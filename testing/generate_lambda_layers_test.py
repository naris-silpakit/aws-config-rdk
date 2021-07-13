import boto3
import subprocess
import sys
import os
from inspect import currentframe

testing_regions = {
    "aws": ["us-east-1", "ap-southeast-1", "eu-central-1", "sa-east-1"],
    "aws-cn": ["cn-north-1", "cn-northwest-1"],
    "aws-us-gov": ["us-gov-west-1", "us-gov-east-1"],
}

rule_list = [
    {"rule": "LP3_TestRule_P38", "runtime": "python3.8"},
    {"rule": "LP3_TestRule_P37", "runtime": "python3.7"},
    {"rule": "LP3_TestRule_P36", "runtime": "python3.6"},
]

sts_client = boto3.client("sts")
arn_array = sts_client.get_caller_identity()["Arn"].split(":")
partition = arn_array[1]
region = arn_array[3]

if region not in testing_regions[partition] and region.strip() != "":
    testing_regions[partition].append(region)

subprocesses = [
    subprocess.Popen(["rdk", "-r", region, "init", "--generate-lambda-layer"]) for region in testing_regions[partition]
]

received_bad_return_code = False

for process in subprocesses:
    process.wait()
    if process.returncode != 0:
        print(process.communicate())
        received_bad_return_code = True

if received_bad_return_code:
    print(f"Error on {currentframe().f_lineno}")
    sys.exit(1)

# Check for generated rdklib-layers
for region in testing_regions[partition]:
    print(region)
    if region != "us-east-1":
        lambda_client = boto3.client("lambda", region_name=region)
    else:
        lambda_client = boto3.client("lambda")
    response = lambda_client.list_layer_versions(LayerName="rdklib-layer")
    if not response["LayerVersions"]:
        print(f"Error on {currentframe().f_lineno}")
        sys.exit(1)

for rule in rule_list:
    os.system(f"rdk create {rule['rule']} --runtime {rule['runtime']}-lib")

# subprocesses = [
#     subprocess.Popen(["rdk", "-r", region, "deploy", "--all", "--generated-lambda-layer"])
# ]
subprocesses = []
for region in testing_regions[partition]:
    os.system(f"rdk -r {region} deploy --all --generated-lambda-layer")
for process in subprocesses:
    process.wait()
    if process.returncode != 0:
        print(process.communicate())
        received_bad_return_code = True

if received_bad_return_code:
    print(f"Error on {currentframe().f_lineno}")
    sys.exit(1)

# Check to see if lambda layers are in use
for region in testing_regions[partition]:
    if region != "us-east-1":
        lambda_client = boto3.client("lambda", region_name=region)
    else:
        lambda_client = boto3.client("lambda")
    layer = lambda_client.get_function()
    for rule in rule_list:
        rulename = rule["rule"].replace("_", "")
        runtime = rule["runtime"]
        lambda_config = lambda_client.get_function(FunctionName=rulename)["Configuration"]
        if runtime != lambda_config["Runtime"]:
            # Make sure to undeploy the rules first if there's an error
            subprocesses = [
                subprocess.Popen(["yes", "|", "rdk", "-r", region, "undeploy", "-a"])
                for region in testing_regions[partition]
            ]
            for process in subprocesses:
                process.wait()
            print(f"Error on {currentframe().f_lineno}")
            sys.exit(1)
        found_layer = False
        for layer in lambda_config["Layers"]:
            if "rdklib-layer" in layer["Arn"]:
                found_layer = True
        if not found_layer:
            # Make sure to undeploy the rules first if there's an error
            subprocesses = [
                subprocess.Popen(["yes", "|", "rdk", "-r", region, "undeploy", "-a"])
                for region in testing_regions[partition]
            ]
            for process in subprocesses:
                process.wait()
            print(f"Error on {currentframe().f_lineno}")
            sys.exit(1)


subprocesses = [
    subprocess.Popen(["yes", "|", "rdk", "-r", region, "undeploy", "-a"]) for region in testing_regions[partition]
]

for process in subprocesses:
    process.wait()
    if process.returncode != 0:
        print(process.communicate())
        received_bad_return_code = True

if received_bad_return_code:
    print(f"Error on {currentframe().f_lineno}")
    sys.exit(1)
