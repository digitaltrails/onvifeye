#!/usr/bin/python3
import json
import logging
import smtplib
import sys
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path

log = logging.getLogger('onvifeye')

def send_mail(send_from, send_to, subject, message, files=[],
              server="localhost", port=587, username='', password='',
              use_tls=True):
    """Compose and send email with provided info and attachments.

    Args:
        send_from (str): from name
        send_to (list[str]): to name(s)
        subject (str): message title
        message (str): message body
        files (list[str]): list of file paths to be attached to email
        server (str): mail server host name
        port (int): port number
        username (str): server auth username
        password (str): server auth password
        use_tls (bool): use TLS mode
    """
    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = ', '.join(send_to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    msg.attach(MIMEText(message))

    for path in files:
        part = MIMEBase('application', "octet-stream")
        with open(path, 'rb') as file:
            part.set_payload(file.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition',
                        'attachment; filename={}'.format(Path(path).name))
        msg.attach(part)

    smtp = smtplib.SMTP(server, port)
    if use_tls:
        smtp.starttls()
    smtp.login(username, password)
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.quit()

def main():
    config_file = Path.home() / '.config' / 'onvifeye-email.conf'
    log.info(f'Reading email config from {config_file.as_posix()}.')
    email_config = None
    with open(config_file) as fp:
        email_config = json.load(fp, strict=False)
        print(email_config)
    if email_config:
        camera_ip = sys.argv[1]
        detections = { k: v for k, v in [a.split('/') for a in sys.argv[2:]] }
        subject = 'Camera detections: ' + ''.join([ f'{k}@{v}' for k, v in detections.items()])
        message = '\n'.join([ f'{k} detected at {v}' for k, v in detections.items()])
        files = []
        attachment = Path.home() / 'onvifeye' / 'images' / camera_ip / f'{list(detections.values())[0]}.jpg'
        for _ in range(10):  # give up after 10 seconds
            if attachment.exists():
                files.append(attachment)
                break
            print("sleeping")
            time.sleep(1)
        send_mail(**email_config, subject=subject, message=message, files=files)

if __name__ == '__main__':
    main()
# finally, don't forget to close the connection