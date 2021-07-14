import boto3
import sys
import subprocess
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
region = arn_array[3].strip()

if(region and region not in testing_regions[partition]):
    testing_regions[partition].append(region)


for region in testing_regions[partition]:
    subprocess.run(f"rdk -r {region} init --generate-lambda-layer", shell=True)

# Check for generated rdklib-layers
for region in testing_regions[partition]:
    print(region)
    lambda_client = boto3.client("lambda", region_name=region)
    response = lambda_client.list_layer_versions(LayerName="rdklib-layer")
    if not response["LayerVersions"]:
        print(f"Error on {currentframe().f_lineno}")
        sys.exit(1)

for rule in rule_list:

    rulename = rule["rule"]
    runtime = rule["runtime"]

    # Create the rule
    out = subprocess.Popen(
        f"rdk create {rulename} --runtime {runtime}-lib --resource-types AWS::EC2::SecurityGroup",
        shell=True,
        stdout=subprocess.DEVNULL,
    )

    out.wait()

    # Deploy the Rule
    processes = [
        {
            "region": region,
            "process": subprocess.Popen(
                f"rdk -r {region} deploy {rulename} --generated-lambda-layer", shell=True, stdout=subprocess.DEVNULL
            ),
        }
        for region in testing_regions[partition]
    ]
    bad_return_code = False
    for process in processes:
        print("Deploying in " + process["region"])
        process["process"].wait()
        if process["process"].returncode != 0:
            bad_return_code = True
    if bad_return_code:
        sys.exit(1)
    # Check to see if lambda layers are in use
    for region in testing_regions[partition]:
        if region != "us-east-1":
            lambda_client = boto3.client("lambda", region_name=region)
        else:
            lambda_client = boto3.client("lambda")
        print("CHECKING IN REGION: "+region.upper())
        rule_lambda_name = "RDK-Rule-Function-" + rule["rule"].replace("_", "")
        lambda_config = lambda_client.get_function(FunctionName=rule_lambda_name)["Configuration"]
        if runtime != lambda_config["Runtime"]:
            print("Deployed a lambda with the wrong runtime, rolling back")
            # Make sure to undeploy the rules first if there's an error
            processes = [
                subprocess.Popen(f"yes | rdk -r {region} undeploy {rulename}", shell=True, stdout=subprocess.DEVNULL)
                for region in testing_regions[partition]
            ]
            for process in processes:
                process.wait()
            sys.exit(1)
        found_layer = False
        for layer in lambda_config["Layers"]:
            if "rdklib-layer" in layer["Arn"]:
                found_layer = True
        if not found_layer:
            print("Deployed a lambda without the required layer, rolling back")
            # Make sure to undeploy the rules first if there's an error
            processes = [
                subprocess.Popen(f"yes | rdk -r {region} undeploy {rulename}", shell=True, stdout=subprocess.DEVNULL)
                for region in testing_regions[partition]
            ]
            for process in processes:
                process.wait()
            sys.exit(1)
    processes = [
        {
            "region": region,
            "process": subprocess.Popen(
                f"yes | rdk -r {region} undeploy {rulename}", shell=True, stdout=subprocess.DEVNULL
            ),
        }
        for region in testing_regions[partition]
    ]
    bad_return_code = False
    for process in processes:
        print("Undeploying in " + process["region"])
        process["process"].wait()
        if process["process"].returncode != 0:
            bad_return_code = True
    if bad_return_code:
        sys.exit(1)
