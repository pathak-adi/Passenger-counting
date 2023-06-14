import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests


def connected_to_internet(url='http://www.google.com/', timeout=5):
    try:
        _ = requests.head(url, timeout=timeout)
        return True
    except requests.ConnectionError:
        print("No internet connection available.")
    return False


def boot_notification():
    # check if connected to internet
    passengers=0
    resp = connected_to_internet()
    if resp:
        date = datetime.now()
        sender_email = "apathak@basi-go.com"
        password = "joxihcqikgknyzas"
        message = MIMEMultipart("alternative")
        message["Subject"] = f"Passenger Counter - Boot Notification at {date}"
        message["From"] = "bibo@basi-go.com"
        html = f"""\
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <title>Title</title>
            </head>
            ​
            <body style="margin: 0; font-family:Arial, sans-serif; background-color:#f3f3f3;">
            <h3>Passenger counter switched on.</h3>
            <br> <p>Initial count: {passengers} passengers. <br> Starting counting process..... </p>
            </body>
            </html>
            """

        part2 = MIMEText(html, "html")

        message.attach(part2)

        # Create secure connection with server and send email
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, password)
            server.sendmail(
                sender_email,
                ["dorishaba@basi-go.com", "jkaseva@basi-go.com", "apathak@basi-go.com"],
                message.as_string()
            )
