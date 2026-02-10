#!/usr/bin/env python3
"""
Configuration Validation Script
Validates all environment variables and service connections
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.core.config import get_settings
from app.core.logging import get_logger
import asyncio

logger = get_logger(__name__)


def validate_llm_keys():
    """Validate LLM API keys."""
    settings = get_settings()
    issues = []

    if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "":
        issues.append("❌ GROQ_API_KEY not set")
    else:
        print(f"✅ GROQ_API_KEY: {settings.GROQ_API_KEY[:20]}...")

    if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == "":
        issues.append("❌ GOOGLE_API_KEY not set")
    else:
        print(f"✅ GOOGLE_API_KEY: {settings.GOOGLE_API_KEY[:20]}...")

    return issues


def validate_aws_config():
    """Validate AWS configuration."""
    settings = get_settings()
    issues = []

    if not settings.AWS_ACCESS_KEY_ID or settings.AWS_ACCESS_KEY_ID == "":
        issues.append("❌ AWS_ACCESS_KEY_ID not set - Transcription will fail!")
    else:
        print(f"✅ AWS_ACCESS_KEY_ID: {settings.AWS_ACCESS_KEY_ID[:20]}...")

    if not settings.AWS_SECRET_ACCESS_KEY or settings.AWS_SECRET_ACCESS_KEY == "":
        issues.append("❌ AWS_SECRET_ACCESS_KEY not set - Transcription will fail!")
    else:
        print(f"✅ AWS_SECRET_ACCESS_KEY: ***{settings.AWS_SECRET_ACCESS_KEY[-4:]}")

    print(f"✅ AWS_REGION: {settings.AWS_REGION}")
    print(f"✅ AWS_S3_BUCKET: {settings.AWS_S3_BUCKET}")

    # Validate transcribe settings
    if settings.TRANSCRIBE_SAMPLE_RATE not in [8000, 16000, 48000]:
        issues.append(f"⚠️  TRANSCRIBE_SAMPLE_RATE={settings.TRANSCRIBE_SAMPLE_RATE} is unusual. Common values: 16000, 48000")
    else:
        print(f"✅ TRANSCRIBE_SAMPLE_RATE: {settings.TRANSCRIBE_SAMPLE_RATE} Hz")

    print(f"✅ TRANSCRIBE_LANGUAGE_CODE: {settings.TRANSCRIBE_LANGUAGE_CODE}")

    return issues


def validate_database():
    """Validate database configuration."""
    settings = get_settings()
    issues = []

    if not settings.DATABASE_URL:
        issues.append("❌ DATABASE_URL not set")
    else:
        # Mask password in output
        masked_url = settings.DATABASE_URL
        if "@" in masked_url:
            parts = masked_url.split("@")
            if ":" in parts[0]:
                user_pass = parts[0].split(":")
                masked_url = f"{user_pass[0]}:***@{parts[1]}"
        print(f"✅ DATABASE_URL: {masked_url}")

    if not settings.CHECKPOINT_DB_URL:
        issues.append("❌ CHECKPOINT_DB_URL not set")
    else:
        masked_url = settings.CHECKPOINT_DB_URL
        if "@" in masked_url:
            parts = masked_url.split("@")
            if ":" in parts[0]:
                user_pass = parts[0].split(":")
                masked_url = f"{user_pass[0]}:***@{parts[1]}"
        print(f"✅ CHECKPOINT_DB_URL: {masked_url}")

    return issues


def validate_interview_config():
    """Validate interview configuration."""
    settings = get_settings()

    print(f"✅ MAX_QUESTIONS_PER_TOPIC: {settings.MAX_QUESTIONS_PER_TOPIC}")
    print(f"✅ READING_TIME_SECONDS: {settings.READING_TIME_SECONDS}s")
    print(f"✅ ANSWER_TIME_SECONDS: {settings.ANSWER_TIME_SECONDS}s")

    # Validate timing makes sense
    issues = []
    if settings.READING_TIME_SECONDS < 10:
        issues.append("⚠️  READING_TIME_SECONDS < 10s might be too short")
    if settings.ANSWER_TIME_SECONDS < 30:
        issues.append("⚠️  ANSWER_TIME_SECONDS < 30s might be too short")

    return issues


def validate_cors():
    """Validate CORS configuration."""
    settings = get_settings()
    origins = settings.cors_origins_list

    print(f"✅ CORS_ORIGINS ({len(origins)} origins):")
    for origin in origins:
        print(f"   - {origin}")

    return []


def validate_email():
    """Validate email configuration."""
    settings = get_settings()
    issues = []

    # Check if RELAY or SMTP is configured
    has_relay = bool(settings.RELAY_HOST and settings.RELAY_HOST != "localhost")
    has_smtp = bool(settings.SMTP_SERVER and settings.SMTP_SERVER != "localhost")

    if has_relay:
        print(f"✅ Email (RELAY): {settings.RELAY_HOST}:{settings.RELAY_PORT}")
        print(f"   From: {settings.EMAILS_FROM_EMAIL}")
        if settings.RELAY_USERNAME:
            print(f"   Username: {settings.RELAY_USERNAME}")
    elif has_smtp:
        print(f"✅ Email (SMTP): {settings.SMTP_SERVER}:{settings.SMTP_PORT}")
    else:
        issues.append("⚠️  No email configuration detected (SMTP/RELAY not set)")

    return issues


async def test_aws_connection():
    """Test AWS connection."""
    settings = get_settings()

    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        print("⚠️  Skipping AWS connection test (credentials not set)")
        return

    try:
        from amazon_transcribe.client import TranscribeStreamingClient

        client = TranscribeStreamingClient(region=settings.AWS_REGION)
        print("✅ AWS TranscribeStreamingClient initialized successfully")
    except Exception as e:
        print(f"❌ AWS connection test failed: {e}")


async def test_database_connection():
    """Test database connection."""
    try:
        from app.core.database import async_engine
        from sqlalchemy import text

        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            await result.fetchone()

        print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")


def main():
    """Run all validation checks."""
    print("\n" + "="*70)
    print("🔍 AI Interview Platform - Configuration Validation")
    print("="*70 + "\n")

    all_issues = []

    # 1. LLM Keys
    print("📝 LLM API Keys")
    print("-" * 70)
    all_issues.extend(validate_llm_keys())
    print()

    # 2. AWS Configuration
    print("☁️  AWS Configuration")
    print("-" * 70)
    all_issues.extend(validate_aws_config())
    print()

    # 3. Database
    print("💾 Database Configuration")
    print("-" * 70)
    all_issues.extend(validate_database())
    print()

    # 4. Interview Config
    print("🎤 Interview Configuration")
    print("-" * 70)
    all_issues.extend(validate_interview_config())
    print()

    # 5. CORS
    print("🌐 CORS Configuration")
    print("-" * 70)
    all_issues.extend(validate_cors())
    print()

    # 6. Email
    print("📧 Email Configuration")
    print("-" * 70)
    all_issues.extend(validate_email())
    print()

    # 7. Connection Tests
    print("🔌 Connection Tests")
    print("-" * 70)
    asyncio.run(test_aws_connection())
    asyncio.run(test_database_connection())
    print()

    # Summary
    print("="*70)
    if not all_issues:
        print("✅ All configuration checks passed!")
    else:
        print(f"⚠️  Found {len(all_issues)} issue(s):")
        for issue in all_issues:
            print(f"   {issue}")
    print("="*70 + "\n")

    return 0 if not all_issues else 1


if __name__ == "__main__":
    sys.exit(main())
