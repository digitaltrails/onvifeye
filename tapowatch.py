#!/usr/bin/python3
"""
tapowatch: TP-Link Tapo-camera ONVIF event monitor and clip recorder
====================================================================



Usage:
======

        tapowatch [--verbose] [camera-config-file]
                  [--help | --detailed-help]

Optional arguments:
-------------------

      -h, --help            show this help message and exit
      --detailed-help       full help in markdown format

Description
===========

Monitor a TP-Link Tapo-camera for ONVIF events and record them using RSTP.
Recording is performed by ffmpeg.

With slight modifications this script would possibly work with other cameras.

Config files
------------

$HOME/.config/tapowatch/tapowatch.


Prerequisites
=============

All the following runtime dependencies are likely to be available pre-packaged on any modern Linux distribution
(``procno`` was originally developed on OpenSUSE Tumbleweed).

* python3
* onvif-zeep-async  (pip install onvif-zeep-async)
* ffmpeg-python (pip install ffmpeg-python)

Procno Copyright (C) 2025 Michael Hamilton
===========================================

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, version 3.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
more details.

You should have received a copy of the GNU General Public License along
with this program. If not, see <https://www.gnu.org/licenses/>.

**Contact:**  m i c h a e l   @   a c t r i x   .   g e n   .   n z

----------
"""
import argparse
import asyncio
import datetime
import json
import logging
import os
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

log = logging.getLogger('tapowatch')

CAMERA_CONF_FILE = Path.home() / '.config' / 'tapowatch' / 'tapowatch.conf'

import ffmpeg
import httpx
from onvif import ONVIFCamera, ONVIFService, ONVIFError
from importlib import resources as imp_resources
from urllib.parse import urlparse, quote
from onvif.managers import PullPointManager

os.environ['OPENCV_FFMPEG_LOGLEVEL'] = '8'
logging.getLogger("httpx").setLevel(logging.CRITICAL)

EXCEPTION_RETRY_WAIT_SECONDS = 5

CAMERA_ONVIF_WSDL_DIR = imp_resources.files('onvif') / 'wsdl'

class CameraConfig(object):
    def __init__(self, camera_username = 'tapo-admin', camera_password = '',
                 camera_ip_addr = '', camera_onvif_port = '2020',
                 camera_stream_name = 'majorStream',
                 camera_clip_seconds = 30,
                 camera_target_events = ('IsPeople', 'IsCar')):
        super().__init__()
        self.camera_username = camera_username
        self.camera_password = camera_password
        self.camera_ip_addr = camera_ip_addr
        self.camera_onvif_port = camera_onvif_port
        self.camera_target_events = camera_target_events
        self.camera_stream_name = camera_stream_name
        self.camera_clip_seconds = camera_clip_seconds

camera_config = CameraConfig()

current_detections = {}


# https://stackoverflow.com/a/75060902/609575
def uri_add_authentication(url, username, password):
    username = quote(username)
    password = quote(password)
    url = urlparse(url)
    netloc = url.netloc.split('@')[-1]
    url = url._replace(netloc=f'{username}:{password}@{netloc}')
    return url.geturl()


class NotificationPuller:

    def __init__(self, onvif_cam: ONVIFCamera):
        self.onvif_cam = onvif_cam
        self.pullpoint_manager: PullPointManager | None  = None
        self.pullpoint_service: ONVIFService | None = None
        self.stop_requested = False
        self.detection_expiry_seconds = 60.0

    async def connect(self):
        while self.pullpoint_service is None:
            try:
                await self.onvif_cam.update_xaddrs()
                interval_time = (datetime.timedelta(seconds=60))
                self.pullpoint_manager = await self.onvif_cam.create_pullpoint_manager(
                    interval_time,
                    subscription_lost_callback=self.recover_subscription)
                self.pullpoint_service = await self.onvif_cam.create_pullpoint_service()
            except httpx.HTTPError as e:
                log.warning(f'Notification Puller http error, will wait. [{repr(e)}]')
                await asyncio.sleep(EXCEPTION_RETRY_WAIT_SECONDS)

    async def recover_subscription(self):
        await self.disconnect()
        await asyncio.sleep(EXCEPTION_RETRY_WAIT_SECONDS)
        await self.connect()

    async def listen(self):
        global current_detections
        while not self.stop_requested:
            if self.pullpoint_service is None:
                await self.connect()
            pullpoint_req = self.pullpoint_service.create_type('PullMessages')
            pullpoint_req.MessageLimit = 5000
            pullpoint_req.Timeout = (datetime.timedelta(days=0, hours=0,
                                                        seconds=self.detection_expiry_seconds))
            try:
                while not self.stop_requested:
                    try:
                        # throws httpx.RemoteProtocolError if it times out
                        camera_messages = await self.pullpoint_service.PullMessages(pullpoint_req)
                        if camera_messages and camera_messages['NotificationMessage']:
                            for notification_msg in camera_messages['NotificationMessage']:
                                data = notification_msg['Message']['_value_1']['Data']
                                for simple_item in data['SimpleItem']:
                                    name, value = simple_item['Name'], simple_item['Value']
                                    if value == "true":
                                        if name not in current_detections:
                                            current_detections[name] = time.time()
                                            log.info(f'added {name} to {current_detections=}')
                        else:
                            await asyncio.sleep(0.1)
                    except httpx.RemoteProtocolError as nothing_ready:
                        log.debug(f'No messages ready. [{repr(nothing_ready)}]')
                        pass
                    finally:
                        now = time.time()
                        for name, first_seen_at in [
                            (name, first_seen_at)
                            for name, first_seen_at in current_detections.items()
                            if now > first_seen_at + self.detection_expiry_seconds]:
                            del current_detections[name]
                            log.info(f"expire '{name}': {first_seen_at} from {current_detections=}")
            except Exception as e:
                log.warning(f'Pull exception, will try again. [{repr(e)}]')
            finally:
                await self.disconnect()

    async def disconnect(self):
        if self.pullpoint_service:
            await self.pullpoint_service.close()
            self.pullpoint_service = None
        if self.pullpoint_manager:
            await self.pullpoint_manager.stop()
            self.pullpoint_manager = None


def ffmpeg_save(rtsp_uri: str, clip_seconds: int):
    save_path = Path.home() / 'tapo-videos' / f'{time.strftime("%Y%m%d-%H%M%S")}.mp4'
    log.info(f"writing {save_path.as_posix()} {current_detections=}")
    save_path.parent.mkdir(exist_ok=True)
    ffmpeg.input(rtsp_uri, t=clip_seconds, loglevel=24).output(
        filename=save_path.as_posix(),
        vcodec='h264', acodec='aac', preset='ultrafast', tune='zerolatency',
        loglevel=8).run()
    log.info(f"closed {save_path.as_posix()}")


class VideoWriter:

    def __init__(self, onvif_cam: ONVIFCamera, stream_name: str, clip_seconds: int):
        super().__init__()
        self.onvif_cam = onvif_cam
        self.stop_requested = False
        self.current_save_path: Path | None = None
        self.stream_name = stream_name
        self.clip_seconds = clip_seconds

    async def save_clips(self):
        while not self.stop_requested:
            try:
                media_service = await self.onvif_cam.create_media_service()
                rtsp_uri = await self._find_rtsp_uri(media_service, self.stream_name)
                while not self.stop_requested:
                    if any(target in current_detections
                           for target in camera_config.camera_target_events):
                        loop = asyncio.get_running_loop()
                        with ProcessPoolExecutor() as pool:
                            await loop.run_in_executor(
                                pool,
                                partial(ffmpeg_save, rtsp_uri, self.clip_seconds))
                    await asyncio.sleep(0.1)
            except ONVIFError as e:
                log.warning(f'Assuming camera is unavailable, will wait [{repr(e)}]')
                await asyncio.sleep(EXCEPTION_RETRY_WAIT_SECONDS)


    async def _find_rtsp_uri(self, media_service, stream_name) -> str:
        rtsp_uri = None
        for profile in await media_service.GetProfiles():
            stream_setup = media_service.create_type('GetStreamUri')
            stream_setup.StreamSetup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
            stream_setup.ProfileToken = profile.token
            uri_data = await media_service.GetStreamUri(stream_setup)
            log.info(f'{profile.Name} {uri_data=}')
            if profile.Name == stream_name:
                log.info(f'Base URL: {uri_data.Uri=}')
                rtsp_uri = uri_add_authentication(uri_data.Uri,
                                                  self.onvif_cam.user, self.onvif_cam.passwd)
        assert rtsp_uri
        return rtsp_uri


async def main():

    def exit_handler(signum, frame):
        log.warning(f'{signal.strsignal(signum)} signalled - exiting')
        notification_puller.stop_requested = True
        video_writer.stop_requested = True
        sys.exit(0)

    signal.signal(signal.SIGHUP, exit_handler)
    signal.signal(signal.SIGINT, exit_handler)

    arg_parser = argparse.ArgumentParser(
        prog='tapowatch',
        description='Monitor a TP-Link Tapo-camera for ONVIF events and record them using RSTP',
        usage='tapowatch.py [--verbose] [camera-config-file]',
        epilog='Copyright Michael Hamilton, GPU GNU General Public License v3.0')
    arg_parser.add_argument('camera_config_file', nargs='?')
    arg_parser.add_argument('-v', '--verbose', action='store_true')  # on/off flag

    args_namespace = arg_parser.parse_args()

    global camera_config

    if args_namespace.camera_config_file:
        config_file = Path(args_namespace.camera_config_file)
    else:
        CAMERA_CONF_FILE.parent.mkdir(exist_ok=True)
        config_file = CAMERA_CONF_FILE

    if not config_file.exists():
        log.warning(f'Created a starter config file {config_file.as_posix()},'
              f' please customise it for your camera.')
        with open(config_file, 'w') as fp:
            json.dump(camera_config, fp, default=vars, indent=4)
        sys.exit(0)
    else:
        log.info(f'Reading config from {config_file.as_posix()}.')
        with open(config_file) as fp:
            camera_config = CameraConfig(**json.load(fp))
            log.debug(f'{camera_config=}')

    onvif_cam = ONVIFCamera(
        camera_config.camera_ip_addr,
        camera_config.camera_onvif_port,
        camera_config.camera_username,
        camera_config.camera_password,
        CAMERA_ONVIF_WSDL_DIR
    )

    notification_puller = NotificationPuller(onvif_cam)
    video_writer = VideoWriter(onvif_cam,
                               stream_name=camera_config.camera_stream_name,
                               clip_seconds=camera_config.camera_clip_seconds)

    await notification_puller.connect()

    async with asyncio.TaskGroup() as watch_task_group:
        _ = watch_task_group.create_task(notification_puller.listen())
        _ = watch_task_group.create_task(video_writer.save_clips())

    await watch_task_group

if __name__ == '__main__':
    asyncio.run(main())
