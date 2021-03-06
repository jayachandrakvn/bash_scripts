#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from colors import color
from pylibs import influxdb
from pylibs import utils
import argparse
import os
import time

SEC_IN_DAY = 60 * 60 * 24  # number of seconds in a day
MAX_CERT_AGE = 90  # maximum certificate age in days
THRESHOLD = 25  # minimum time before expiration alert


def save_to_influxdb(timestamp, domain, check_result: bool):
    try:
        json_body = [{
            "time": timestamp,
            "measurement": "monitoring-certificate",
            "tags": {'domain': domain},
            "fields": {'check_result': check_result}
        }]
        client = influxdb.InfluxDBClient(args.influxdb_host, args.influxdb_port, args.influxdb_user,
                                         args.influxdb_password, args.influxdb_database)
        client.write_points(json_body, time_precision='s')
        utils.message('Domain {}, check result {} was saved to InfluxDB on timestamp {}'.
                      format(domain, check_result, timestamp))
    except BaseException:
        utils.message('Error saving domain {}, check result {} to InfluxDB on timestamp {}!'.
                      format(domain, check_result, timestamp))


def print_check_result(domain, age_file_check, age_cert_check, check_result: bool):
    if check_result:
        print(color('[PASS] {}, file age check {}, cert age check {}, result: {}'.format(
            domain, age_file_check, age_cert_check, check_result), fg='white', bg='green', style='bold'))
    else:
        print(color('[FAIL] {}, file age check {}, cert age check {}, result: {}'.format(
            domain, age_file_check, age_cert_check, check_result), fg='white', bg='red', style='bold'))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Get SSL certificates expiration info')

    parser.add_argument('-d', '--domains', nargs='+', metavar='example.com example.org', default=os.environ.get(
        'DOMAINS', []), help='Domains to check certificates on. Use whitespace to separate domains. '
                             'Do not use schemes (http, https). If this option is not set, '
                             'DOMAINS environment variable is used')

    parser.add_argument('-p', '--path', nargs=1, metavar='PATH', default=os.environ.get(
        'CERTBOT_ETC_PATH', os.environ.get('LETSENCRYPT_ETC_PATH', ['/etc/letsencrypt'])),
                        help='Path to certbot/letsencrypt certificate directory. If not passed, '
                             'CERTBOT_ETC_PATH or LETSENCRYPT_ETC_PATH environment variable are used '
                             '(CERTBOT_ETC_PATH take precedence), if none of them are present, '
                             '/etc/letsencrypt used as default')

    parser.add_argument('--save-to-influxdb', action='store_true', help='Save domains check results to influxdb '
                                                                        'or just output them to console')

    influxdb.add_influxdb_options(parser)

    args = parser.parse_args()

    domains_traversed = {}  # we will set True for domain traversed in filesystem loop
    t = time.time()
    file_threshold = SEC_IN_DAY * (MAX_CERT_AGE - THRESHOLD)
    for entry in os.scandir(args.path[0].rstrip(os.sep) + '/live'):
        if not entry.name.startswith('.') and entry.is_dir():
            age_file_check = t - entry.stat().st_mtime < file_threshold
            age_cert_check = utils.get_cert_expiration_timestamp(entry.name) - t > THRESHOLD
            check_result = age_file_check and age_cert_check
            domains_traversed[entry.name] = True
            if args.save_to_influxdb:
                save_to_influxdb(t, entry.name, check_result)
            else:
                print_check_result(entry.name, age_file_check, age_cert_check, check_result)

    for domain in args.domains:
        if domain not in domains_traversed:
            age_cert_check = utils.get_cert_expiration_timestamp(domain) - t > THRESHOLD
            if args.save_to_influxdb:
                save_to_influxdb(t, domain, age_cert_check)
            else:
                print_check_result(domain, 'unavailable', age_cert_check, age_cert_check)
