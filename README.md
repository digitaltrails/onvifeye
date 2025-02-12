onvifeye: ONVIF event monitor and clip recorder
===============================================

___This code works, I'm using it to monitor a camera, but
it is still work in progress.___

Onvifeye is a camera ONVIF python client that monitors TP-Link Tapo-C225,
saving videos, jpegs, and raising emails.  

THe script may work with other cameras, but might require modification
to cope with camera specific event data.

Onvifeye includes the following functions:

 - Monitoring for event types (for example, IsPerson, IsPet, IsMotion).
 - Download of video clips of events via RSTP (Tapo-C225 RSTP majorStream or minorStream).
 - Clips are encoded in MPEGTS streaming format so they can be viewed while downloading.
 - Download of jpegs via RSTP (mini preview imags Tapo-C225 RSTP jpegStream).
 - Events may trigger the execution of an external script.
 - An example external script is provided. It sends an email with a jpeg attachment.
 - Fast encoding by using ffmpeg.
 - Multiple cameras can be monitored, each with its own config file.

The script was developed on Linux, but may be able to work on 
any platform that supports the required python libraries.  It's currently 
running on OpenSUSE Tumbleweed (AMD x86-64) and Raspbian (Raspberry Pi 5).

Feedback is welcome.

Required libraries
===================

Beyond standard Python3, the following additional libraries are required:
 - onvif-zeep-async (pip install onvif-zeep-async)
 - ffmpeg-python (pip install ffmpeg-python). __Take care not to confuse
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
_IsPerson=True_ as all part of a single event.  If a following notification
lacks _IsPerson=True_, or if there are no following notifications within
60 seconds, the event expires.

Getting Started
---------------

To get started with ``onvifeye``, you only need to download the ``onvideye.py`` 
python script and check that the dependencies described above are in place. 

If you want to events to send emails you'll also need the ``onvifemail.py``
script.

### Installing the program

Depending on you Linux distribution, the required dependencies may not be
available via your disto's normall installation mechanism.  You might have
to use _pip_ to install them locally in a python-virtual environment under
a normal user account, for example:

```commandline
# Create a python virtual environment, for example:

python3 -m venv ~/onvif-venv
~/onvif-venv/bin/pip3 install onvif-zeep-async
~/onvif-venv/bin/pip3 install ffmpeg-python
 install ffmpeg-python
```

### Executing the program

No special permissions are required, just use a normal account.
Assuming you're using the python venv created above, the script
can be setup and run as follows:

First create some template config files for one or more cameras:

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
    "camera_clip_seconds": 60,
    "camera_target_events": [
        "IsPeople",
        "IsCar"
    ],
    "camera_event_exec": "/home/michael/bin/onvifeye-email.py",
    "camera_save_folder": "/home/michael/onvifeye"
}
```

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
the camera config file (see example camera config file above), then start
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
touch ~/onvifeye/images/10.36.184.128/20250209-134428.jpg

# Invoke the script, pass it a camera-id and the detection/date-time from above:
# (the id can be anything you like, it doesn't have to be an actual camera id)
python3 ~/Projects/onvifeye/onvifeye-email.py DummyCameraId IsPerson/20250209-134428
```

User systemd service
--------------------

I'm experimenting with running the script as a systemd user service.

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

A camera going offline may cause the script to stop working, I need
to track down and handle any exceptions that occur.

Something from ffmpeg seems to write to the tty in a way that makes it
unusable to the point where, after terminating the script, I have to log 
out of the terminal/ssh-session and log back in. I need to track this
down and prevent it.

When an event occurs, due to time delays receiving and processing the 
ONVIF notification, the script might not capture video for the very
beginning of the event.

I expect that cameras other than the C225 may report detection events 
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
  TP-Link Community Support for responding so rapidy to my enquiries
  concerning missing ONVIF detection data. A 48-hour response with new
  firmware - quite remarkable.
