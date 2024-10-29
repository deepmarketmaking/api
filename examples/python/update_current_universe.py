import boto3
import asyncio
import json
from sys import argv
import websockets
from authenticate import authenticate_user
from datetime import datetime

# Initialize S3 client
s3 = boto3.client('s3')

# Define S3 bucket and file details
bucket_name = 'deepmm.public'
file_key = 'bond_data.json'

# Download the JSON file
try:
    # Get the JSON file from S3
    response = s3.get_object(Bucket=bucket_name, Key=file_key)
    data = json.loads(response['Body'].read().decode('utf-8'))

    # Extract FIGI values
    figis = [item["F"] for item in data if "F" in item]
    print("FIGI values:", figis)

except Exception as e:
    print(f"Error: {e}")


# Get the current UTC time with milliseconds
utc_now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
print(utc_now)

# Now we will attempt to call the Deep MM API with the extracted FIGI values
# And remove all figis from this list which are unrecognized by the API

if len(argv) < 3:
    print('Usage: python update_current_universe.py <Deep MM dev username> <password>')
    exit()

username = argv[1]
password = argv[2]

# Now in in UTC timestamp format as shown below




template = {
    'rfq_label': 'spread',
    'quantity': 1_000_000,
    'side': 'bid',
    'ats_indicator': "N",
    'subscribe': False,
    'timestamp': ['2023-11-01T15:10:07.661Z']
}

# Create a list of the above dictionary, one entry with the 'figi' key for each FIGI in the above list
msg = {'inference': [dict(template, figi=figi) for figi in figis]}

async def get_inferences(figis, msg):
    msg['token'] = authenticate_user(username, password)
    ws = await websockets.connect("wss://staging1.deepmm.com")
    await ws.send(json.dumps(msg))
    for i in range(5):
        response = await ws.recv()
        # Parse the response as JSON
        response_json = json.loads(response)

        if 'unrecognized_figis' in response_json:
            unrecognized_figis = response_json['unrecognized_figis']

            # Filter the unrecognized FIGIs from the list of FIGIs
            figis = [figi for figi in figis if figi not in unrecognized_figis]

            # Now we need to create a new file which is just the new list of FIGIs
            # and then upload it to s3:
            # s3://deepmm.public/universe.txt

            import csv
            import io

            # Now we need to create a new file which is just the new list of FIGIs
            # and then upload it to s3:
            # s3://deepmm.public/universe.txt

            # Create a CSV file in memory with the updated list of FIGIs
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer, lineterminator='\n')
            for figi in figis:
                csv_writer.writerow([figi])

            # Upload the CSV file to S3
            s3.put_object(
                Bucket='deepmm.public',
                Key='universe.txt',
                Body=csv_buffer.getvalue(),
                ContentType='text/txt'
            )

            print("Updated FIGIs successfully uploaded to S3 as universe.csv.")

            break
        
# Call get_inferences function and wait until complete
asyncio.run(get_inferences(figis, msg))

