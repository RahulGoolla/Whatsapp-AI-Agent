from app.core.config import settings
from app.core.logging import logger
from app.storage.base import BaseStorage


class S3Storage(BaseStorage):
    """
    AWS S3 storage driver implementation.
    Ready for activation in production environments.
    """

    def __init__(self) -> None:
        self.bucket = settings.AWS_S3_BUCKET
        self.region = settings.AWS_S3_REGION
        logger.info(
            f"AWS S3 Storage driver configured for bucket: {self.bucket} in region {self.region}"
        )

        # Boto3 client initialization placeholder:
        # import boto3
        # self.s3_client = boto3.client(
        #     "s3",
        #     aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        #     aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        #     region_name=self.region
        # )

    async def upload_file(
        self, file_content: bytes, filename: str, path_prefix: str = ""
    ) -> str:
        """Uploads file content directly to S3 bucket."""
        # s3_key = f"{path_prefix}/{filename}" if path_prefix else filename
        # try:
        #     await anyio.to_thread.run_sync(
        #         self.s3_client.put_object,
        #         Bucket=self.bucket,
        #         Key=s3_key,
        #         Body=file_content
        #     )
        #     return s3_key
        # except Exception as e:
        #     raise StorageError(message="S3 Upload Failed") from e
        raise NotImplementedError(
            "AWS S3 Storage driver is defined but not yet enabled."
        )

    async def download_file(self, storage_key: str) -> bytes:
        """Retrieves file bytes from S3 bucket."""
        # try:
        #     response = await anyio.to_thread.run_sync(
        #         self.s3_client.get_object,
        #         Bucket=self.bucket,
        #         Key=storage_key
        #     )
        #     return response["Body"].read()
        # except Exception as e:
        #     raise StorageError(message="S3 Download Failed") from e
        raise NotImplementedError(
            "AWS S3 Storage driver is defined but not yet enabled."
        )

    async def delete_file(self, storage_key: str) -> None:
        """Removes a file from S3 bucket."""
        # try:
        #     await anyio.to_thread.run_sync(
        #         self.s3_client.delete_object,
        #         Bucket=self.bucket,
        #         Key=storage_key
        #     )
        # except Exception as e:
        #     raise StorageError(message="S3 Deletion Failed") from e
        raise NotImplementedError(
            "AWS S3 Storage driver is defined but not yet enabled."
        )
