from flask import Flask, request, jsonify
import boto3, json
import deboost_runner
import deboost
import numpy as np

app = Flask(__name__)
s3 = boto3.client('s3')


@app.route('/analysis', methods=['POST'])
def data_analysis():
    if request.method == 'POST':
        data = request.json
        user_name = data['summonerName']
        bucket_name = data['bucketName']
        object_key_list = data['keyNames']
        input_data_list = []
        for key in object_key_list:
            response = s3.get_object(Bucket=bucket_name, Key=key)
            file_content = response['Body'].read().decode('utf-8')
            data = json.loads(file_content)
            input_data_list.append(data)

        result = deboost.main(input_data_list, user_name)
        # result = deboost_runner.run(data)
        result = np.round(result*100, 2).astype(float).tolist()
        result = [round(x, 3) for x in result]
        print(result)
        return jsonify(data=result)


if __name__ == '__main__':
    # app.run()
    app.run(host='0.0.0.0', port=5000)