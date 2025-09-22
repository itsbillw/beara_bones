import json
import pandas as pd
from minio import Minio
from minio.error import S3Error

# Initialize MinIO client
client = Minio(
    "minio.itsbillw.eu",  # Replace with your server address
    access_key="1A19PXSQM0GFQW3BBGGQ",
    secret_key="49fI8bRutSPk+vubo8pytvxUi6n2nYDH77OUaVuT",
    secure=True  # Set to True if using HTTPS
)

# Read a file from your bucket
try:
    # Get object from bucket
    response = client.get_object("raw", "fixtures/liverpool/fixtures_liverpool_2025_20250922.json")

    # Read the data
    file_content = response.read()

    # If it's a text file, decode it
    json_data = json.loads(file_content.decode('utf-8'))

    df = pd.json_normalize(json_data["response"])
    df = df[df["fixture.status.short"]=="FT"]

    print("DataFrame shape:", df.shape)
    print("\nColumn names:")
    print(df.columns.tolist())
    print("\nFirst few rows:")
    print(df.head(15))

    # Don't forget to close the response
    response.close()
    response.release_conn()

except S3Error as err:
    print(f"MinIO Error: {err}")
except json.JSONDecodeError as err:
    print(f"JSON parsing error: {err}")
except Exception as err:
    print(f"General error: {err}")