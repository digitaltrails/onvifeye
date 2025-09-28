#!/usr/bin/python3
import json
import logging
import smtplib
import sys
import time
from email.message import EmailMessage
from email.utils import make_msgid
from email.utils import formatdate
from pathlib import Path
from typing import List

log = logging.getLogger('onvifemail')

def send_mail(send_from: str, send_to: List[str],
              subject: str, message: str, jpeg_filename: Path,
              server="localhost", port=587, username='', password='', add_legal_stuff=False):
    msg = EmailMessage()
    msg['From'] = send_from
    msg['To'] = ", ".join(send_to)
    msg['Subject'] = subject
    msg['Date'] = formatdate(localtime=True)

    attachment_cid = make_msgid()

    boilerplate = """
     Please notify the sender immediately by e-mail if you have 
     received this e-mail by mistake and delete this e-mail from
     your system. If you are not the intended recipient, you are 
     notified that disclosing, copying, distributing or taking 
     any action in reliance on the contents of this information 
     is strictly prohibited.""" if add_legal_stuff else ''

    msg.set_content(f'{message}\n\n{boilerplate}')
    html_message = message.replace("\n","<br/>")
    msg.add_alternative(f'<html><body><br/><b>{html_message}</b><br/><br/>'
                        f'<img src="cid:{attachment_cid}"/>'
                        f'<br/><br/>{boilerplate}</body></html>',
                        'html')

    if jpeg_filename:
        with open(jpeg_filename, "rb") as fd:
            msg.get_payload()[1].add_related(fd.read(), 'image', 'jpeg', cid=attachment_cid)

    smtp_connection = smtplib.SMTP(host=server, port=port)
    smtp_connection.starttls()
    smtp_connection.login(username, password)
    smtp_connection.sendmail(send_from, send_to, msg.as_string())
    smtp_connection.close()

# The sys.argv arguments expected to be: camera-id detectionType/yyyymmdd-hhmmss
# For example: python3 onvifeye-email.py c125-1 IsPerson/20250928-125933
# The detection type and date-time is used in the email subject.  T
# The jpeg is attached to the email.
# The jpeg is expected to found in $HOME/onvifeye/camera-id/yyyymmdd-hhmmss.jpg
# In this example, the jpeg should be in $HOME/onvifeye/c125-1/20250928-125933.jpg
# The script will loop testing for jpeg to be written for 10 seconds and then give
# up waiting and email anyway.
def main():
    config_file = Path.home() / '.config' / 'onvifeye' / 'onvifeye-email.conf'
    log.info(f'Reading email config from {config_file.as_posix()}.')
    email_config = None
    with open(config_file) as fp:
        email_config = json.load(fp, strict=False)
        log.info(email_config)
    if email_config:
        camera_id = sys.argv[1]
        detections = { k: v for k, v in [a.split('/') for a in sys.argv[2:]] }
        subject = f'Camera {camera_id} detected ' + ','.join(
            [ f'{k.removeprefix("Is").lower()} at {v}' for k, v in detections.items()])
        message = (f'Camera: {camera_id}\n\n' +
                   '\n'.join([ f'{k.removeprefix("Is")} detected at {v}'
                              for k, v in detections.items()]))
        attach_filename = None
        jpeg_filename = Path.home() / 'onvifeye' / camera_id / f'{list(detections.values())[0]}.jpg'
        log.info(f"looking for {jpeg_filename.as_posix()}")
        # print(f"looking for {jpeg_filename.as_posix()}")
        for _ in range(10):  # give up after 10 seconds
            if jpeg_filename.exists():
                attach_filename = jpeg_filename
                break
            print("sleeping")
            time.sleep(1)
        #print(attach_filename)
        send_mail(**email_config, subject=subject, message=message, jpeg_filename=attach_filename)

if __name__ == '__main__':
    main()
