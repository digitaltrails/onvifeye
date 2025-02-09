#!/usr/bin/python3
import json
import logging
import smtplib
import sys
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path
from typing import List

log = logging.getLogger('onvifemail')

def send_mail(send_from: str, send_to: List[str],
              subject: str, message: str, files: List[Path],
              server="localhost", port=587, username='', password=''):
    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = ", ".join(send_to)
    msg['Subject'] = subject
    msg['Date'] = formatdate(localtime=True)
    msg.attach(MIMEText(message))
    for file_path in files:
        with open(file_path, "rb") as fd:
            ext = file_path.suffix
            attachment = MIMEApplication(fd.read(), _subtype=ext)
            attachment.add_header(
                'content-disposition', 'attachment', filename=file_path.name)
        msg.attach(attachment)
    smtp_connection = smtplib.SMTP(host=server, port=port)
    smtp_connection.starttls()
    smtp_connection.login(username, password)
    smtp_connection.sendmail(send_from, send_to, msg.as_string())
    smtp_connection.close()


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
        files = []
        attachment = Path.home() / 'onvifeye' / 'images' / camera_id / f'{list(detections.values())[0]}.jpg'
        print(attachment.as_posix())
        for _ in range(10):  # give up after 10 seconds
            if attachment.exists():
                files.append(attachment)
                break
            print("sleeping")
            time.sleep(1)
        send_mail(**email_config, subject=subject, message=message, files=files)

if __name__ == '__main__':
    main()
