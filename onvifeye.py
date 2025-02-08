#!/usr/bin/python3
"""
onvifeye: ONVIF event monitor and clip recorder
===============================================

Usage:
======

        onvifeye [--verbose] [--create] [camera-config-file]
                  [--help | --detailed-help]

Optional arguments:
-------------------

      -h, --help            show this help message and exit
      --detailed-help       full help in Markdown format

Description
===========

Monitor for camera ONVIF events and record them using RSTP.
Recording is performed by ffmpeg.

Currently only tested against a TP-Link Tapo-C225.  With slight modifications
this script will likely work with other cameras.

Run initially by supplying command line parameters to create a config file.

Config files
------------

$HOME/.config/onvifeye/onvifeye default camera config


Prerequisites
=============

* python3
* onvif-zeep-async (pip install onvif-zeep-async)
* ffmpeg-python (pip install ffmpeg-python). Take care not to confuse
  ffmpeg-python with python-ffmpeg the two are different ffmpeg python
  implementations.

onvifeye Copyright (C) 2025 Michael Hamilton
=============================================

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
import json
import logging
import os
import signal
import sys
from datetime import datetime, timedelta
from time import time
from abc import abstractmethod
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path
from typing import Dict

from wsdiscovery import Scope, QName
from wsdiscovery.discovery import ThreadedWSDiscovery as WSDiscovery

log = logging.getLogger('onvifeye')

CAMERA_CONF_FILE = Path.home() / '.config' / 'onvifeye' / 'onvifeye.conf'

import ffmpeg
import httpx
from onvif import ONVIFCamera, ONVIFService, ONVIFError
from importlib import resources as imp_resources
from urllib.parse import urlparse, quote
from onvif.managers import PullPointManager

import smtplib
from email.mime.text import MIMEText

os.environ['OPENCV_FFMPEG_LOGLEVEL'] = '8'
logging.getLogger("httpx").setLevel(logging.CRITICAL)

EXCEPTION_RETRY_WAIT_SECONDS = 5

CAMERA_ONVIF_WSDL_DIR = imp_resources.files('onvif') / 'wsdl'

class CameraConfig(object):
    def __init__(self, camera_username = 'tapo-admin', camera_password = '',
                 camera_ip_addr = '', camera_onvif_port = '2020',
                 camera_stream_name = 'majorStream',
                 camera_stills_stream_name = 'jpegStream',
                 camera_clip_seconds = 30,
                 camera_target_events = ('IsPeople', 'IsCar')):
        super().__init__()
        self.camera_username = camera_username
        self.camera_password = camera_password
        self.camera_ip_addr = camera_ip_addr
        self.camera_onvif_port = camera_onvif_port
        self.camera_target_events = camera_target_events
        self.camera_stream_name = camera_stream_name
        self.camera_stills_stream_name = camera_stills_stream_name
        self.camera_clip_seconds = camera_clip_seconds

camera_config = CameraConfig()

# https://stackoverflow.com/a/75060902/609575
def uri_add_authentication(url, username, password):
    username = quote(username)
    password = quote(password)
    url = urlparse(url)
    netloc = url.netloc.split('@')[-1]
    url = url._replace(netloc=f'{username}:{password}@{netloc}')
    return url.geturl()


class TargetCamera:

    def __init__(self, onvif_camera: ONVIFCamera):
        super().__init__()
        self.onvif = onvif_camera
        self.detections: Dict[str, datetime] = {}


class NotificationPuller:

    def __init__(self, target_camera: TargetCamera):
        self.target_camera = target_camera
        self.pullpoint_manager: PullPointManager | None  = None
        self.pullpoint_service: ONVIFService | None = None
        self.stop_requested = False
        self.detection_expiry_seconds = 60.0

    async def connect(self):
        while self.pullpoint_service is None:
            try:
                await self.target_camera.onvif.update_xaddrs()
                interval_time = (timedelta(seconds=60))
                self.pullpoint_manager = await self.target_camera.onvif.create_pullpoint_manager(
                    interval_time,
                    subscription_lost_callback=self.recover_subscription)
                self.pullpoint_service = await self.target_camera.onvif.create_pullpoint_service()
            except httpx.HTTPError as e:
                log.warning(f'Notification Puller http error, will wait. [{repr(e)}]')
                await asyncio.sleep(EXCEPTION_RETRY_WAIT_SECONDS)

    async def recover_subscription(self):
        await self.disconnect()
        await asyncio.sleep(EXCEPTION_RETRY_WAIT_SECONDS)
        await self.connect()

    async def listen(self):
        while not self.stop_requested:
            if self.pullpoint_service is None:
                await self.connect()
            pullpoint_req = self.pullpoint_service.create_type('PullMessages')
            pullpoint_req.MessageLimit = 5000
            pullpoint_req.Timeout = (timedelta(days=0, hours=0,
                                               seconds=self.detection_expiry_seconds))
            try:
                while not self.stop_requested:
                    try:
                        # throws httpx.RemoteProtocolError if it times out
                        camera_messages = await self.pullpoint_service.PullMessages(pullpoint_req)
                        if camera_messages and camera_messages['NotificationMessage']:
                            for notification_msg in camera_messages['NotificationMessage']:
                                if log.isEnabledFor(logging.DEBUG):  # Avoid expensive debugging
                                    log.debug(f"Notification {notification_msg=}")
                                data = notification_msg['Message']['_value_1']['Data']
                                for simple_item in data['SimpleItem']:
                                    name, value = simple_item['Name'], simple_item['Value']
                                    if value == "true":
                                        if name not in self.target_camera.detections:
                                            self.target_camera.detections[name] = datetime.now()
                                            log.info(f'added {name} to {self.target_camera.detections=}')
                        else:
                            await asyncio.sleep(0.1)
                    except httpx.RemoteProtocolError as nothing_ready:
                        log.debug(f'No messages ready. [{repr(nothing_ready)}]')
                        pass
                    finally:
                        now = datetime.now()
                        for name, first_seen_at in [
                            (name, first_seen_at)
                            for name, first_seen_at in self.target_camera.detections.items()
                            if (now - first_seen_at).seconds > self.detection_expiry_seconds]:
                                del self.target_camera.detections[name]
                                log.info(f"expire '{name}': {first_seen_at} -> {self.target_camera.detections=}")
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


def save_video(camera_name:str, rtsp_uri: str, clip_seconds: int, detections: Dict[str, datetime]):
    save_path = (Path.home() / 'onvif-videos' / f'{camera_name}' /
                 f'{list(detections.values())[0].strftime("%Y%m%d-%H%M%S")}.mp4')
    log.info(f"writing {save_path.as_posix()}")
    save_path.parent.parent.mkdir(exist_ok=True)
    save_path.parent.mkdir(exist_ok=True)
    if save_path.exists():
        log.error(f'Skipping save. Save file already exists: {save_path}')
        return
    try:  # using mpegts so it can be previewed as it's being created.
        out, err = ffmpeg.input(rtsp_uri, t=clip_seconds, loglevel=24).output(
            filename=save_path.as_posix(), f='mpegts',
            vcodec='h264', acodec='aac', preset='ultrafast', tune='zerolatency',
            loglevel=8).run(capture_stdout=True, capture_stderr=True)
        if out or err:
            log.error(f"{err} {err.stdout.decode('utf8')=} {err.stderr.decode('utf8')=}")
    except ffmpeg.Error:
        log.error(f"{err} {err.stdout.decode('utf8')=} {err.stderr.decode('utf8')=}")
        return
    log.info(f"closed {save_path.as_posix()}")


def save_image(camera_name:str, rtsp_uri: str, detections: Dict[str, datetime]):
    save_path = (Path.home() / 'onvif-images' / f'{camera_name}' /
                 f'{list(detections.values())[0].strftime("%Y%m%d-%H%M%S")}.jpg')
    log.info(f'writing {save_path.as_posix()}')
    save_path.parent.parent.mkdir(exist_ok=True)
    save_path.parent.mkdir(exist_ok=True)
    if save_path.exists():
        log.error(f'Skipping save. Save file already exists: {save_path}')
        return
    try:
        out, err = ffmpeg.input(rtsp_uri, loglevel=24).output(
            filename=save_path.as_posix(), frames=1,
            loglevel=32).run()#(capture_stdout=True, capture_stderr=True)
        if out or err:
            log.error(f"{err} {err.stdout.decode('utf8')=} {err.stderr.decode('utf8')=}")
    except ffmpeg.Error as e:
        log.error(f"ffmpeg error {e}")
        return
    log.info(f'closed {save_path.as_posix()}')


def execute_external_handler(handler_exe: Path, relevant_detections: Dict[str, datetime]):
    pass

class EventHandler:

    def __init__(self, target_camera: TargetCamera):
        super().__init__()
        self.stop_requested = False
        self.target_camera = target_camera
        self.handled: Dict[str, datetime] = {}

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
                                                  self.target_camera.onvif.user,
                                                  self.target_camera.onvif.passwd)
        return rtsp_uri

    def has_been_handled(self, detections: Dict[str, datetime]):  # has this time been handled already
        for event, etime in detections.items():
            if event in self.handled and self.handled[event] == etime:
                return True
        return False

    def mark_as_handled(self, detections: Dict[str, datetime]):
        for event, etime in detections.items():
            self.handled[event] = etime

    @abstractmethod
    async def handle_events(self):
        pass


class VideoWriter(EventHandler):

    def __init__(self, target_camera: TargetCamera, stream_name: str, clip_seconds: int):
        super().__init__(target_camera)
        self.stream_name = stream_name
        self.clip_seconds = clip_seconds

    async def handle_events(self):
        while not self.stop_requested:
            try:
                media_service = await self.target_camera.onvif.create_media_service()
                if rtsp_uri := await self._find_rtsp_uri(media_service, self.stream_name):
                    log.debug(f'{rtsp_uri=}')
                    while not self.stop_requested:
                        if relevant_detections := {event: etime
                                                   for event, etime in self.target_camera.detections.items()
                                                   if event in camera_config.camera_target_events}:
                            loop = asyncio.get_running_loop()
                            if not self.has_been_handled(relevant_detections):
                                with ProcessPoolExecutor() as pool:
                                    await loop.run_in_executor(
                                        pool,
                                        partial(save_video, self.target_camera.onvif.host,
                                                rtsp_uri, self.clip_seconds, relevant_detections))
                            self.mark_as_handled(relevant_detections)  # update
                        await asyncio.sleep(0.1)
                else:
                    log.info("Camera doesn't appear to be active, will wait.")
                    await asyncio.sleep(EXCEPTION_RETRY_WAIT_SECONDS)
            except ONVIFError as e:
                log.warning(f'Assuming camera is unavailable, will wait [{repr(e)}]')
                await asyncio.sleep(EXCEPTION_RETRY_WAIT_SECONDS)


class ImageWriter(EventHandler):

    def __init__(self, target_camera: TargetCamera, stream_name: str):
        super().__init__(target_camera)
        self.stream_name = stream_name

    async def handle_events(self):
        while not self.stop_requested:
            try:
                media_service = await self.target_camera.onvif.create_media_service()
                if rtsp_uri := await self._find_rtsp_uri(media_service, self.stream_name):
                    log.debug(f'{rtsp_uri=}')
                    while not self.stop_requested:
                        if relevant_detections := {event: etime
                                                   for event, etime in self.target_camera.detections.items()
                                                   if event in camera_config.camera_target_events}:
                            loop = asyncio.get_running_loop()
                            if not self.has_been_handled(relevant_detections):
                                with ProcessPoolExecutor() as pool:
                                    await loop.run_in_executor(
                                        pool,
                                        partial(save_image, self.target_camera.onvif.host, rtsp_uri,
                                                relevant_detections))
                            self.mark_as_handled(relevant_detections)
                        await asyncio.sleep(0.1)
                else:
                    log.info("Camera doesn't appear to be active, will wait.")
                    await asyncio.sleep(EXCEPTION_RETRY_WAIT_SECONDS)
            except ONVIFError as e:
                log.warning(f'Assuming camera is unavailable, will wait [{repr(e)}]')
                await asyncio.sleep(EXCEPTION_RETRY_WAIT_SECONDS)


class EventExecHandler(EventHandler):

    def __init__(self, target_camera: TargetCamera, handler_exe: Path):
        super().__init__(target_camera)
        self.handler_exe = handler_exe

    async def handle_events(self):
        while not self.stop_requested:
            if relevant_detections := {event: etime
                                       for event, etime in self.target_camera.detections.items()
                                       if event in camera_config.camera_target_events}:
                loop = asyncio.get_running_loop()
                with ProcessPoolExecutor() as pool:
                    await loop.run_in_executor(
                        pool,
                        partial(execute_external_handler, self.handler_exe, relevant_detections))
            await asyncio.sleep(0.1)


async def discover_devices():
    wsd = WSDiscovery(ttl=4, relates_to=True)
    wsd.start()
    services = wsd.searchServices(types=[
                QName(
                    "http://www.onvif.org/ver10/network/wsdl",
                    "NetworkVideoTransmitter",
                    "dp0",
                )], scopes=[Scope('onvif://www.onvif.org/Profile/Streaming')])
    for service in services:
        print(service.getEPR() + ":" + service.getXAddrs()[0])
    wsd.stop()
    print('done devices')
    #sys.exit(0)

async def main():

    await discover_devices()

    def exit_handler(signum, frame):
        log.warning(f'{signal.strsignal(signum)} signalled - exiting')
        notification_puller.stop_requested = True
        video_writer.stop_requested = True
        sys.exit(0)

    signal.signal(signal.SIGHUP, exit_handler)
    signal.signal(signal.SIGINT, exit_handler)

    global camera_config

    arg_parser = argparse.ArgumentParser(
        prog='onvifeye',
        description='Monitor a TP-Link Tapo-camera for ONVIF events and record them using RSTP',
        usage='onvifeye.py [--verbose] [config-overrides] [camera-config-file]',
        epilog='Copyright Michael Hamilton, GPU GNU General Public License v3.0')
    arg_parser.add_argument('camera_config_files', nargs='+')
    arg_parser.add_argument('-c', '--create-config', type=Path, help='create a new config file from arguments')
    arg_parser.add_argument('-v', '--verbose', action='store_true')  # on/off flag
    arg_parser.add_argument('-e', '--event-exec', type=Path, help='on event execute program' )

    for key, value in vars(camera_config).items():
        arg_parser.add_argument(f'--{key}', type=type(value), required=False)

    args_namespace = arg_parser.parse_args()

    if args_namespace.verbose:
        log.setLevel(logging.DEBUG)

    camera_configs_list = []

    if args_namespace.camera_config_files:
        for config_filename in args_namespace.camera_config_files:
            config_file = Path(config_filename)
            log.info(f'Reading config from {config_file.as_posix()}.')
            with open(config_file) as fp:
                camera_config = CameraConfig(**json.load(fp))
            for arg, value in vars(args_namespace).items():  # override from command line args - if any
                if arg != 'camera_config_files' and value:
                    print(f'{arg=}{value=}')
                    parts = value.split(':')  # Syntax is ip_addr:value or value
                    ip_addr, value = [None, parts[1]] if len(parts) == 1 else parts
                    if ip_addr is None or ip_addr == camera_config.camera_ip_addr:
                        log.warning(f'Overriding {config_filename} {arg} with command line value.')
                        vars(camera_config)[arg] = value
            log.debug(f'{vars(camera_config)}')
            camera_configs_list.append(camera_config)
    # else:
    #     CAMERA_CONF_FILE.parent.mkdir(exist_ok=True)
    #     config_file = CAMERA_CONF_FILE



    # if not config_file.exists():
    #     log.warning(f'Created a starter config file {config_file.as_posix()},'
    #           f' please customise it for your camera.')
    #     for arg, value in vars(args_namespace).items:  # initialise from command line args - if any
    #         vars(camera_config)[arg] = value
    #     with open(config_file, 'w') as fp:
    #         json.dump(camera_config, fp, default=vars, indent=4)
    #     sys.exit(0)
    # else:
    #     log.info(f'Reading config from {config_file.as_posix()}.')
    #     with open(config_file) as fp:
    #         camera_config = CameraConfig(**json.load(fp))
    #     for arg, value in vars(args_namespace).items():  # override from command line args - if any
    #         if value:
    #             vars(camera_config)[arg] = value
    #     log.debug(f'{vars(camera_config)}')

    target_camera_list = []



    for camera_config in camera_configs_list:
        target_camera = TargetCamera(
            ONVIFCamera(
                camera_config.camera_ip_addr,
                camera_config.camera_onvif_port,
                camera_config.camera_username,
                camera_config.camera_password,
                CAMERA_ONVIF_WSDL_DIR
            ))
        target_camera_list.append(target_camera)


    async with asyncio.TaskGroup() as watch_task_group:
        for target_camera in target_camera_list:
            notification_puller = NotificationPuller(target_camera)
            _ = watch_task_group.create_task(notification_puller.listen())
            if camera_config.camera_stills_stream_name:
                image_writer = ImageWriter(target_camera,
                                           stream_name=camera_config.camera_stills_stream_name)
                _ = watch_task_group.create_task(image_writer.handle_events())
            if camera_config.camera_stream_name:
                video_writer = VideoWriter(target_camera,
                                           stream_name=camera_config.camera_stream_name,
                                           clip_seconds=camera_config.camera_clip_seconds)
                _ = watch_task_group.create_task(video_writer.handle_events())


    await watch_task_group

if __name__ == '__main__':
    asyncio.run(main())
