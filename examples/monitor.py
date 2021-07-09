import json
import os
import threading
from time import sleep
from typing import Union

import requests
from absl import app
from absl import flags
from absl import logging
from mailthon import postman, email

from mercari import Mercari

FLAGS = flags.FLAGS

flags.DEFINE_list('keywords', None, 'Keywords separated by a comma.')
flags.DEFINE_list('max_prices', None, 'Maximum price for each item separated by a comma.')
flags.DEFINE_list('min_prices', None, 'Minimum price for each item separated by a comma.')
flags.DEFINE_bool('disable_gmail', False, '')
flags.DEFINE_bool('disable_alertzy', False, '')
flags.DEFINE_string('alertzy_key', None, 'Get your key here https://alertzy.app/')


class Alertzy:

    def __init__(self):
        self.use_module = True
        self.lock = threading.Lock()
        self.alertzy_key = FLAGS.alertzy_key
        if not self.alertzy_key:
            self.use_module = False
            logging.warning('Alertzy was not configured. Notifications will not be sent to your '
                            'iPhone through the Alertzy app.')
        else:
            self.send_notification('Monitoring has started.', title='Mercari')

    def send_notification(self, message, title, url=None, image_url=None):
        # https://alertzy.app/
        if self.use_module:
            with self.lock:
                assert self.alertzy_key is not None
                try:
                    requests.post('https://alertzy.app/send', data={
                        'accountKey': self.alertzy_key,
                        'title': title,
                        'message': message,
                        'link': url,
                        'image': image_url,
                    })
                except Exception:
                    return False
                return True


class GMailSender:
    def __init__(self):
        self.use_module = True
        self.lock = threading.Lock()
        gmail_config_filename = 'gmail_conf.json'
        if os.path.isfile(gmail_config_filename):
            with open(gmail_config_filename, 'r') as gmail:
                gmail_constants = json.load(gmail)
                self.gmail_password = gmail_constants['gmail_password']
                self.gmail_user = gmail_constants['gmail_user']
                if '@' not in self.gmail_user:
                    logging.error('Gmail user should be a GMAIL address.')
                    exit(1)
                self.recipients = [x.strip() for x in gmail_constants['recipients'].strip().split(',')]
            self.send_email_notification('Mercari', 'Monitoring has started.')
        else:
            self.use_module = False
            logging.warning('Gmail is not configured. If you want to receive email notifications, '
                            'copy gmail_conf.json.example to gmail_conf.json and edit the constants. '
                            'I advise you to create a new Gmail account, just for this purpose.')

    def send_email_notification(self, email_subject, email_content, attachment=None):
        if self.use_module:
            with self.lock:
                if attachment is not None:
                    attachment = [attachment]
                else:
                    attachment = ()
                for recipient in self.recipients:
                    p = postman(host='smtp.gmail.com', auth=(self.gmail_user, self.gmail_password))
                    r = p.send(email(content=email_content,
                                     subject=email_subject,
                                     sender='{0} <{0}>'.format(self.gmail_user),
                                     receivers=[recipient],
                                     attachments=attachment))
                    logging.info(f'Email subject is {email_subject}.')
                    logging.info(f'Email content is {email_content}.')
                    logging.info(f'Attachment located at {attachment}.')
                    logging.info(f'Notification sent from {self.gmail_user} to {recipient}.')
                    assert r.ok


class MonitorKeyword:
    def __init__(self, keyword, price_min: int, price_max: int,
                 gmail_sender: Union[None, GMailSender],
                 alertzy: Union[None, Alertzy]):
        self.keyword = keyword
        self.price_min = price_min
        self.price_max = price_max
        self.gmail_sender = gmail_sender
        self.alertzy = alertzy
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.mercari = Mercari()
        self.persisted_items = []

    def join(self):
        self.thread.join()

    def start_monitoring(self):
        self.thread.start()

    def scrape_outstanding_items(self):
        items = self.mercari.fetch_all_items(
            keyword=self.keyword,
            price_min=self.price_min,
            price_max=self.price_max,
            max_items_to_fetch=100
        )
        self.persisted_items.extend(items)
        logging.info(f'{len(items)} items found for {self.mercari.name}.')
        logging.info(f'{len(self.persisted_items)} items found in total.')

    def check_for_new_items(self):
        items_on_first_page = self.mercari.fetch_items_pagination(
            keyword=self.keyword,
            price_min=self.price_min,
            price_max=self.price_max
        )
        new_items = set(items_on_first_page) - set(self.persisted_items)
        for new_item in new_items:
            logging.debug(f'[{self.keyword}] New Url: {new_item}.')
            self.persisted_items.append(new_item)
            item = self.mercari.get_item_info(new_item)
            if self.keyword.lower() in item.name.lower() and item.is_new and item.in_stock:
                logging.debug(f'[{self.keyword}] New item detected: {new_item}.')
                email_subject = f'{item.name} {item.price}'
                email_subject_with_url = f'{email_subject} {item.url}'
                email_content = f'{item.url}<br/><br/>{item.desc}'
                attachment = item.local_url
                if self.alertzy is not None:
                    logging.info('Will send an Alertzy notification.')
                    self.alertzy.send_notification(email_subject_with_url,
                                                   title=self.keyword,
                                                   url=item.url,
                                                   image_url=item.url_photo)
                else:
                    logging.info('Will skip Alertzy.')
                if self.gmail_sender is not None:
                    logging.info('Will send a GMAIL notification.')
                    self.gmail_sender.send_email_notification(email_subject, email_content, attachment)

    # noinspection PyBroadException
    def _run(self):
        logging.info(f'[{self.keyword}] Starting monitoring with price_max: {self.price_max} '
                     f'and price_min: {self.price_min}.')
        self.scrape_outstanding_items()
        time_between_two_requests = 60
        logging.info(f'We will check the first page(s) every {time_between_two_requests} seconds '
                     f'and look for new items.')
        logging.info('The program has started to monitor for new items...')
        while True:
            sleep(time_between_two_requests)
            try:
                self.check_for_new_items()
            except Exception:
                logging.exception('exception')
                sleep(30)


def main(argv):
    logging.set_verbosity(logging.INFO)
    os.makedirs(FLAGS.log_dir, exist_ok=True)
    logging.get_absl_handler().use_absl_log_file()
    assert len(FLAGS.min_prices) == len(FLAGS.max_prices)
    assert all([int(m1) < int(m2) for m1, m2 in zip(FLAGS.min_prices, FLAGS.max_prices)])
    gmail = None if FLAGS.disable_gmail else GMailSender()
    alertzy = None if FLAGS.disable_alertzy else Alertzy()
    monitors = []
    for keyword, min_price, max_price in zip(FLAGS.keywords, FLAGS.min_prices, FLAGS.max_prices):
        monitors.append(MonitorKeyword(keyword.strip(), min_price, max_price, gmail, alertzy))
    for monitor in monitors:
        monitor.start_monitoring()
        sleep(5)  # delay the start between them.
    # wait forever.
    for monitor in monitors:
        monitor.join()


if __name__ == '__main__':
    app.run(main)
