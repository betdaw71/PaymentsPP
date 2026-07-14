import boto3
from botocore.exceptions import NoCredentialsError
import dotenv
import os
from io import BytesIO

dotenv.load_dotenv()

BUCKET_NAME = os.getenv('BUCKET_NAME')
S3_ENDPOINT = os.getenv('S3_ENDPOINT')
ACCESS_KEY = os.getenv('ACCESS_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')


def upload_to_s3(file, object_name):
    s3_client = boto3.client('s3',
                             endpoint_url=S3_ENDPOINT,
                             aws_access_key_id=ACCESS_KEY,
                             aws_secret_access_key=SECRET_KEY)

    s3_client.upload_fileobj(BytesIO(file), BUCKET_NAME, object_name)

    file_url = f"{S3_ENDPOINT}/{BUCKET_NAME}/{object_name}"
    return file_url
