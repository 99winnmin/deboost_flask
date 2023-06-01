from flask import Flask, request
import boto3, json
import deboost_runner

app = Flask(__name__)
s3 = boto3.client('s3')


@app.route('/analysis', methods=['POST'])
def data_analysis():
    if request.method == 'POST':
        data = request.json
        bucket_name = data['bucketName']
        object_key = data['objectKey']
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        file_content = response['Body'].read().decode('utf-8')
        data = json.loads(file_content)
        result = deboost_runner.run(data)
        print(result)
        return result


if __name__ == '__main__':
    app.run()
