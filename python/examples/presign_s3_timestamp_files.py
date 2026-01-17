import boto3
from botocore.client import Config

# Initialize S3 client with the correct region and credentials
s3_client = boto3.client('s3', region_name='us-east-1', config=Config(signature_version='s3v4'))

# Parameters
bucket = 'deepmm.temp'
prefix = 'nathan/historical/twice_a_day/'
expires_in = 604800  # 7 days in seconds

# List objects in the bucket
response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)

# Generate presigned URLs for each object
for obj in response.get('Contents', []):
    key = obj['Key']
    presigned_url = s3_client.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': bucket,
            'Key': key,
            'ResponseContentDisposition': 'inline'  # Matches console behavior
        },
        ExpiresIn=expires_in
    )
    print(presigned_url)
