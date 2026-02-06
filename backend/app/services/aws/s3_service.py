"""AWS S3 service for file storage."""

import boto3
import uuid
from io import BytesIO
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self.bucket = settings.AWS_S3_BUCKET

    async def upload_resume(self, file_bytes: bytes, filename: str, candidate_id: str) -> str:
        """Upload resume to S3 and return URL."""
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "pdf"
        key = f"resumes/{candidate_id}/{uuid.uuid4()}.{ext}"
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=BytesIO(file_bytes),
                ContentType=self._content_type(ext),
                ServerSideEncryption="AES256",
            )
            url = f"s3://{self.bucket}/{key}"
            logger.info(f"Uploaded resume: {url}")
            return url
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            raise

    async def upload_audio(self, audio_bytes: bytes, interview_id: str, seq: int) -> str:
        """Upload raw audio chunk to S3."""
        key = f"raw-audio/{interview_id}/{seq:06d}.webm"
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=BytesIO(audio_bytes),
                ContentType="audio/webm",
                ServerSideEncryption="AES256",
            )
            return f"s3://{self.bucket}/{key}"
        except Exception as e:
            logger.error(f"Audio upload failed: {e}")
            raise

    async def store_transcript(self, text: str, interview_id: str, q_num: int) -> str:
        """Store transcript text to S3."""
        key = f"transcripts/{interview_id}/q{q_num:03d}.txt"
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType="text/plain",
            ServerSideEncryption="AES256",
        )
        return f"s3://{self.bucket}/{key}"

    async def download_file(self, s3_url: str) -> bytes:
        """Download a file from S3 by its s3:// URL."""
        bucket, key = self._parse_s3_url(s3_url)
        response = self.s3_client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def generate_presigned_url(self, s3_url: str, expiration: int = 3600) -> str:
        """Generate a presigned URL to download a file from S3.
        
        Args:
            s3_url: The s3:// URL of the file.
            expiration: URL expiration time in seconds (default 1 hour).
        
        Returns:
            A presigned HTTPS URL for downloading the file.
        """
        bucket, key = self._parse_s3_url(s3_url)
        return self.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expiration
        )

    @staticmethod
    def _parse_s3_url(url: str) -> tuple:
        path = url.replace("s3://", "")
        parts = path.split("/", 1)
        return parts[0], parts[1]

    @staticmethod
    def _content_type(ext: str) -> str:
        mapping = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "doc": "application/msword",
            "txt": "text/plain",
        }
        return mapping.get(ext.lower(), "application/octet-stream")


def get_s3_service() -> S3Service:
    return S3Service()
