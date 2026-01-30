onvifeye: ONVIF event monitor and clip recorder
===============================================

> [!NOTE]
> This code is now mature. I'm using it to monitor three different 
> models of Tapo cameras, but there are relatively few users, so your 
> millage may vary.

Onvifeye is a camera ONVIF python client that monitors TP-Link Tapo-C225,
Tapo-C125, and maybe others.  It saves videos, jpegs, and raises emails.  

THe script may work with other cameras, but might require modification
to cope with camera-specific event data.

Onvifeye includes the following functions:

 - Monitoring for event types (for example, IsPerson, IsPet, IsMotion).
 - Download of video clips of events via RSTP (Tapo-C225/C125 RSTP majorStream or minorStream).
 - Clips are encoded in MPEGTS streaming format so they can be viewed while downloading.
 - Download of jpegs via RSTP (mini preview imags Tapo-C225/C125 RSTP jpegStream).
 - Events may trigger the execution of an external script.
 - An example external script is provided. It sends an email with a jpeg attachment.
 - Fast encoding by using ffmpeg.
 - Multiple cameras can be monitored, each with its own config file.

The script was developed on Linux, but may be able to work on 
any platform that supports the required python libraries.  It's currently 
running on OpenSUSE Tumbleweed (AMD x86-64) and Raspbian (Raspberry Pi 5).

Feedback is welcome.

Cameras and Camera Firmware
===========================

I'm using the following cameras with the noted firmware versions:

  - Tapo-C225(EU) Ver 2.0 Firmware 1.1.0 Build 250115 Rel 47645n
  - Tapo-C125(EU) Ver 1.0 Firmware 1.3.2 Build 241122 Rel 43589n
  - Tapo-C320WS(EU) Ver 2.2 Firmware 1.3.5 Build 250522 Rel.4563n

The script is also report to work with the CS310.

Required libraries
===================

Beyond standard Python3, the following additional libraries are required:
 - onvif-zeep-async (pip install onvif-zeep-async)
 - ffmpeg-python (pip3 install ffmpeg-python). __Take care not to confuse
   ffmpeg-python with python-ffmpeg the two are different ffmpeg python
   implementations.__

Description
-----------

Onvifeye works by pulling notifications from ONVIF feed.  When notified
of detection event, the ONVIF related RSTP feed is used to stream video
and jpegs to local storage, plus an optional external handling script/program
may be triggered.

Onvifeye may handle a series of continuous detection notifications as a single
event. For example, onvifeye regards a series of notifications that include
_IsPerson=True_ as part of a single event.  If a following notification
lacks _IsPerson=True_, or if there are no following notifications within
60 seconds, the event expires.

Getting Started
---------------

To get started with ``onvifeye``, you only need to download the ``onvideye.py`` 
python script and check that the dependencies described above are in place. 

If you want to events to send emails you'll also need the ``onvifemail.py``
script.

### Installing the program

Depending on your Linux distribution, the required dependencies may not be
available via your distro's normal installation mechanism.  You might have
to use _pip_ to install them locally in a python-virtual environment under
a normal user account, for example:

```commandline
# Create a python virtual environment, for example:

python3 -m venv ~/onvif-venv
~/onvif-venv/bin/pip3 install onvif-zeep-async
~/onvif-venv/bin/pip3 install ffmpeg-python
```

### Executing the program

No special permissions are required, just use a normal account.
Assuming you're using the python venv created above, the script
can be setup and run as follows:

First, create some template config files for one or more cameras:

```commandline
# Create starter config files for any cameras you wish to monitor:
~/onvif-venv/bin/python3 onvifeye.py --create c225-1.conf
~/onvif-venv/bin/python3 onvifeye.py --create c225-2.conf
```

Edit the created config files in `$HOME/.config/onvifeye/cameras/*.conf`,
set the camera access username, password, ip-address, and any other
properties that differ from the defaults, for example:

```commandline
{
    "camera_username": "cam-admin",
    "camera_password": "SuperSecretPassword",
    "camera_id": "c225-1",
    "camera_model": "c225",
    "camera_ip_addr": "10.0.0.128",
    "camera_onvif_port": "2020",
    "camera_stream_name": "mainStream",
    "camera_stills_stream_name": "jpegStream",
    "camera_clip_seconds": 60,
    "camera_target_events": [
        "IsPeople",
        "IsCar"
    ],
    "camera_event_exec": "/home/michael/bin/onvifeye-email.py",
    "camera_save_folder": "/home/michael/onvifeye",
    "camera_grab_stills_from_video": true
}
```
The latest commit includes a new setting `camera_grab_stills_from_video`,
which defaults to `true`.  This setting forces the script to grab still images from
videos saved from `camera_stream_name`. This may be preferable to grabbing them 
from the `camera_stills_stream_name` because it's bound to work for more cameras, 
plus the images are grabbed full size.  If set to `false` the stills stream 
will be used as before.

Run with the configured config files, for example:

```

~/onvif-venv/bin/python3 onvifeye.py

```
If you need to stop the script, use control-C (sigterm) or sighup.

Create some events by moving around in front of the camera. After any event,
check for new videos or images:

```
ls -lart $HOME/onvifeye/images $HOME/onvifeye/videos
ls -lart $HOME/onvifeye/images $HOME/onvifeye/images
```

To enable SMTP emails, create and edit `$HOME/.config/onvifeye/onvifeye-email.conf`,
the contents should resemble:
```commandline
{
    "send_from": "cam-admin",
    "send_to": [ "me@somewhere.blah" ],
    "server": "pop.myisp.com",
    "username": "memyself",
    "password": "somethinghardtoguess"
}
```

Make the email script executable and check its location is properly set in
the camera config file (see the example camera config file above), then start
or restart the main script:

```
# set permissions:
chmod u+x /where/ever/you/put/onvifeye-email.py

# Restart
~/onvif-venv/bin/python3 onvifeye.py
```

The email script can also be tested stand alone, for example:
```commandline
# Create a dummy image for a date-time
touch ~/onvifeye/images/DummyCameraId/20250209-134428.jpg

# Invoke the script, pass it a camera-id and the detection/date-time from above:
# (the id can be anything you like, it doesn't have to be an actual camera id)
python3 ~/Projects/onvifeye/onvifeye-email.py DummyCameraId IsPerson/20250209-134428
```

 > [!WARNING]
 > The email script is currently hard coded to expect images and videos to be
 > in the default location (edit the script to change it).

Use in the presense of a Tapo 500 Hub
-------------------------------------

The __Tapo H500 hub__ defaults to setting each camera to fallback the H500's own 
private WiFi SID/network when the camera's user-assigned WiFi SID/network 
becomes unavailable (or is measured as having a poor RSSI value?). 

> [!IMPORTANT]
> If a camera does fallback to the H500's WiFi, then the ONVIF feed will no
> longer be visible on the user assigned WiFi SID/network.

You can disable H500-WiFi fallback on a camera by camera basis under 
the H500's _Manage Connected-Devices_. for each camera, set _WiFi 
backup_ to off.

You can tell if a camera is connecting to an H500's SID by checking the 
SID listed for the Tapo App's _Camera-Settings Network-Connection_.  
Additionally, touching the _WiFi-icon_ in the _Camera-Settings 
Network-Connectioin_ will toggle the display of the measured RSSI
(which can be handy when deciding where to place a camera).

I'm unsure if a Camera will return to the user assigned WiFi when
the RSSI improves, or whether a reboot of the camera is requited.
I suspect the latter.

User systemd service
--------------------

I'm experimenting with running the script as a systemd user service.
I've had the service running for about a month with no issues, it 
handles the camera going in and out of private mode, it has been 
saving videos and sending emails for person-detection events.

I set up a user service that lingers after logout and linger also means 
it will restart on a reboot.  I set up a user such as ovadmin, installed
the scripts and the required environment, and set the user to linger.
```commandline
loginctl enable-linger ovadmin
loginctl list-users
 UID USER  LINGER
1000 ovadmin yes

1 users listed.
```
The `/home/ovadmin/.config/systemd/user/onvifeye.service` unit file is as follows:
```commandline
[Unit]
Description=onvifeye
StartLimitIntervalSec=30
StartLimitBurst=2

[Service]
ExecStart=/home/ovadmin/onvif-venv/bin/python3 /home/ovadmin/onvifeye.py
Restart=on-failure

[Install]
WantedBy=default.target
```
Enable the user service:
```
systemctl --user daemon-reload
systemctl --user enable onvifeye
```
Start the service and check if it started, and look in the journal for logging:
```commandline
systemctl --user start onvifeye
systemctl --user status onvifeye
journalctl --user --boot
# tail the accumulating log:
journalctl --user --boot --follow
```

Issues
------

A camera going offline may sometimes cause the script to stop working, I need
to track down and handle any exceptions that occur.  This may be due to
cameras falling back from user WiFi to Tapo H500 Hub WiFi - needs further
investigation.

Something from ffmpeg seems to write to the tty in a way that makes it
unusable after terminating the script.  I've now added code to check if
either stdin or stout is a tty, if yes, the tty attributes are saved
at startup and restored at exit. This should hopefully solve the
issue if/when in occurs (but this is untested).

Due to time delays receiving and processing ONVIF notification, the 
script might not capture video for the very beginning of an event.

I expect that cameras other than the C225/C125 may report detection events 
differently.  The code needs to be enhanced to abstract/separate the 
detection-parsing so it is determined by camera-model.

The json parsing of config files doesn't produce very friendly error
messages when the syntax is wrong.

Authors
-------

Michael Hamilton\
``m i c h a e l   @  a c t r i x   .   g e n  . n z``


Version History
---------------

License
-------

This project is licensed under the **GNU General Public License Version 3** - see the [LICENSE.md](LICENSE.md) file 
for details

**Onvifeye Copyright (C) 2025 Michael Hamilton**

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, version 3.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
more details.

You should have received a copy of the GNU General Public License along
with this program. If not, see <https://www.gnu.org/licenses/>.

## Acknowledgments

* I learnt how to use onvif-zeep-async by studying Peter Stamp's 
  [TAPO-camera-ONVIF-RTSP-and-AI-Object-Recognition](
  https://github.com/peterstamps/TAPO-camera-ONVIF-RTSP-and-AI-Object-Recognition).
* Thanks go out to Graham Huang, TP-Link Support, and Solla-topee, 
  TP-Link Community Support for responding so rapidly to my enquiries
  concerning missing ONVIF detection data. A 48-hour response with new
  firmware, quite remarkable.
* @jb1923 for feedback, including reporting that the C310 camera works
  with the script.
