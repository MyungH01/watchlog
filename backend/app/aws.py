"""S3·SQS 호출. 인증은 boto3 기본 체인, 엔드포인트는 AWS_ENDPOINT_URL 환경 변수를 boto3가 직접 읽는다."""
import json
from functools import cache

import boto3
from botocore.config import Config

from . import config


@cache
def s3():
    return boto3.client("s3")


@cache
def _s3_public():
    # 서명 URL은 브라우저가 쓰므로, 브라우저에서 보이는 주소로 서명해야 한다
    return boto3.client(
        "s3", endpoint_url=config.S3_PUBLIC_ENDPOINT_URL, config=Config(signature_version="s3v4")
    )


@cache
def sqs():
    return boto3.client("sqs")


def upload_form(key: str, content_type: str, max_bytes: int) -> dict:
    """브라우저가 S3로 직접 올릴 때 쓰는 {url, fields}. 크기와 형식을 S3가 강제한다."""
    return _s3_public().generate_presigned_post(
        config.S3_BUCKET,
        key,
        Fields={"Content-Type": content_type},
        Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, max_bytes]],
        ExpiresIn=config.UPLOAD_URL_SECONDS,
    )


def view_url(key: str) -> str:
    return _s3_public().generate_presigned_url(
        "get_object", Params={"Bucket": config.S3_BUCKET, "Key": key}, ExpiresIn=3600
    )


def object_size(key: str) -> int | None:
    try:
        return s3().head_object(Bucket=config.S3_BUCKET, Key=key)["ContentLength"]
    except s3().exceptions.ClientError:
        return None


def download(key: str, path: str) -> None:
    s3().download_file(config.S3_BUCKET, key, path)


def delete_objects(keys: list[str]) -> None:
    for i in range(0, len(keys), 1000):
        s3().delete_objects(
            Bucket=config.S3_BUCKET, Delete={"Objects": [{"Key": k} for k in keys[i : i + 1000]]}
        )


def enqueue(measurement_id: str) -> None:
    sqs().send_message(
        QueueUrl=config.SQS_QUEUE_URL, MessageBody=json.dumps({"measurement_id": measurement_id})
    )
