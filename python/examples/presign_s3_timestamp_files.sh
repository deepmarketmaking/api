# First, copy files to S3 (replace with your source path and S3 URL)
#aws s3 cp ./*.gz s3://deepmm.temp/nathan/historical/twice_a_day/ --recursive

# Then, generate presigned URLs for each file (valid for 1 week = 604800 seconds)
for file in $(aws s3 ls s3://deepmm.temp/nathan/historical/twice_a_day/ --recursive | awk '{print $4}'); do
    aws s3 presign s3://deepmm.temp/$file --expires-in 604800
done
