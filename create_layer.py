import subprocess
import os
import uuid
import sys
import shutil
import boto3

folder_name = "lib" + str(uuid.uuid4())
shell_command = "pip3 install --target ./python boto3 botocore rdk rdklib"
sts_client = boto3.client("sts")
arn_array = sts_client.get_caller_identity()["Arn"].split(":")
partition = arn_array[1]
region = boto3.session.Session().region_name
s3_client = boto3.client("s3", region_name=region)
s3_resource = boto3.resource("s3", region_name=region)
lambda_client = boto3.client("lambda", region_name=region)
rdk_lib_layer = "rdklib-layer"

print("Checking Lambda for Existing RDK Layer")
response = lambda_client.list_layer_versions(LayerName=rdk_lib_layer)
if response["LayerVersions"]:
    print(
        f"Found rdklib-layer with version {response['LayerVersions'][0]['LayerVersionArn']}"
    )
elif not response["LayerVersions"]:
    print("No rdklib-layer found")

print("-l/--lambda-layer Flag received, forcing update of the Lambda Layer")

print(f"Installing Packages to {folder_name}/python")
try:
    os.makedirs(folder_name + "/python")
except FileExistsError as e:
    print(e)
    sys.exit(1)
os.chdir(folder_name)
ret = subprocess.run(shell_command, capture_output=True, shell=True)

print("Creating rdk_lib_layer.zip")
shutil.make_archive("rdk_lib_layer", "zip", "python")
os.chdir("..")


print("Creating temporary S3 Bucket")
bucket_name = "rdkliblayertemp" + str(uuid.uuid4())
if region != "us-east-1":
    s3_client.create_bucket(
        Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": region}
    )
if region == "us-east-1":
    s3_client.create_bucket(Bucket=bucket_name)

print("Uploading rdk_lib_layer.zip to S3")
s3_resource.Bucket(bucket_name).upload_file(
    f"{folder_name}/rdk_lib_layer.zip", "rdklib-layer"
)

print("Publishing Lambda Layer")
lambda_client.publish_layer_version(
    LayerName="rdklib-layer",
    Content={"S3Bucket": bucket_name, "S3Key": "rdklib-layer"},
    CompatibleRuntimes=["python3.6", "python3.7", "python3.8"],
)

print("Deleting temporary S3 Bucket")
try:
    bucket = s3_resource.Bucket(bucket_name)
    bucket.objects.all().delete()
    bucket.delete()
except Exception as e:
    print(e)

print("Cleaning up temp_folder")
shutil.rmtree(f"./{folder_name}")
