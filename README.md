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

Executing the program
---------------------

```commandline
python3 onvifeye.py --create c225-1.conf
python3 onvifeye.py --create c225-2.conf
# edit the created config files in $HOME/.config/onvifeye/cameras/*.conf

# run with the configured config files:
python3 onvifeye.py

# After any event, check:
ls $HOME/onvifeye/images $HOME/onvifeye/videos

# To enable emails
# edit $HOME/.config/onvifeye/onvifeye-email.conf

chmod u+x /where/ever/you/put/onvifeye-email.py
# edit a camera config file and set camera_event_exec to /where/ever/you/put/onvifeye-email.py

# Restart
python3 onvifeye.py
```

Sample config files
-------------------

#### Camera config 
`$HOME/.config/onvifeye/cameras/c225-1.conf`

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

#### onvifeye-email config 
`$HOME/.config/onvifeye/onvifeye-email.conf`
```commandline
{
    "send_from": "cam-admin",
    "send_to": [ "me@somewhere.blah" ],
    "server": "pop.myisp.com",
    "username": "memyself",
    "password": "somethinghardtoguess"
}
```

Issues
------

A camera going offline can cause the script to stop working, I need
to track down and handle any exceptions that occur.

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
