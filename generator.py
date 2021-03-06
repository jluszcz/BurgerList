#!/usr/bin/env python

import argparse
import boto3
import htmlmin
import jinja2
import json
import logging
import os
import tempfile

from botocore.exceptions import ClientError

CARD_IMAGE_LOCATION = 'images/card.png'


def _get_file_for_read(file_name, bucket=None, local=False):
    if local:
        return file_name

    f = tempfile.NamedTemporaryFile(delete=False)
    logging.debug('Downloading %s to %s', file_name, f.name)
    bucket.download_fileobj(file_name, f)
    return f.name


def _get_file_for_write(file_name, local=False):
    if local:
        return file_name

    return tempfile.NamedTemporaryFile(delete=False).name


def _read_template(template_file):
    return jinja2.Template(template_file.read())


def read_template(bucket=None, local=False):
    with open(_get_file_for_read('index.template', bucket, local)) as f:
        return _read_template(f)


def _read_list(list_file):
    return json.load(list_file)


def read_list(bucket=None, local=False):
    with open(_get_file_for_read(f"{os.environ['SITE']}.json", bucket, local)) as f:
        return _read_list(f)


def _card_image_exists(site_bucket, local):
    if not site_bucket:
        return False

    try:
        site_bucket.Object(CARD_IMAGE_LOCATION).load()
        return True
    except ClientError as e:
        if e.response['Error']['Code'] != '404':
            logging.warn('Failed to check existence of %s: %s', CARD_IMAGE_LOCATION, e)
        return False


def write_index(template, list_data, site_bucket=None, local=False, minify=True):
    filename = _get_file_for_write('index.html', local)

    template_data = {
        'title': list_data['title'],
        'lists': list_data['lists'],
        'card_url':  None,
    }

    if _card_image_exists(site_bucket, local):
        template_data['card_url'] = f"https://{os.environ['SITE_URL']}/{CARD_IMAGE_LOCATION}"

    rendered_site = template.render(**template_data)

    if minify:
        rendered_site = htmlmin.minify(rendered_site, remove_comments=True, remove_empty_space=True)
        logging.debug('Minified index.html')

    with open(filename, 'w') as f:
        f.write(rendered_site)

    if not local:
        logging.debug('Uploading index.html')
        with open(filename, 'r') as f:
            site_bucket.put_object(Key='index.html', Body=f.read(), ContentType='text/html')


def parse_args():
    parser = argparse.ArgumentParser(description='List of lists website generator')
    parser.add_argument('--verbose', '-v', dest='verbose', action='store_true', help='If provided, log at DEBUG instead of INFO.')
    parser.add_argument('--s3', action='store_true', help='If provided, use S3 rather than local files.')

    return parser.parse_args()


def setup_logging(verbose=False):
    """Sets up logging using the default python logger, at INFO or DEBUG, depending on the value of verbose"""

    logger = logging.getLogger()
    logger.setLevel(logging.INFO if not verbose else logging.DEBUG)
    for boto_module in ['boto3', 'botocore', 's3transfer']:
        logging.getLogger(boto_module).setLevel(logging.CRITICAL)


def get_bucket(bucket_name, local=False):
    if local:
        return None

    s3 = boto3.resource('s3')
    return s3.Bucket(bucket_name)


def write_index_to_bucket(local=False):
    gen_bucket = get_bucket(f"{os.environ['SITE_URL']}-generator", local)
    site_bucket = get_bucket(os.environ['SITE_URL'], local)

    template = read_template(gen_bucket, local)
    list_data = read_list(gen_bucket, local)

    write_index(template, list_data, site_bucket, local)


def lambda_handler(event, context):
    """Entry point for Lambda"""
    setup_logging()
    write_index_to_bucket()


def main():
    """Entry point for running as a CLI"""
    args = parse_args()
    setup_logging(args.verbose)
    write_index_to_bucket(local=not args.s3)


if __name__ == '__main__':
    main()
