# import requests
#
# api_url = "https://api.pdva0.xyz/api/v1/"
#
# endpoint_login = 'auth/login/'
# endpoint_2fa_setup = 'auth/2fa-setup/'
# endpoint_solutions = 'merchant/merchant-fees/'
#
# url = api_url + endpoint_login
#
# data = {
#     "username": "head_support_1",
#     "password": "Proverka1",
#     "code": "866834"
# }
#
# response = requests.post(url, json=data)
# print(response.text)
# access_token = response.json()['access']
# refresh_token = response.json()['refresh']
#
# print(access_token)
#
# headers = {
#     "Authorization": f"Bearer {access_token}"
# }
#
# # url = api_url + endpoint_2fa_setup
# # response = requests.get(url, headers=headers)
# #
# # print(response.raw)
# # print(response.status_code)
# # print(response.text)
#
# url = api_url + endpoint_solutions
#
# data = {
#     "payment_system": 'cf2f5db2-4cdb-4309-8391-7c07a279d030',
#     "merchant": 'eb86c308-4ca1-4dda-8abc-d16c6c75dfb2',
#     "mdr_in": 6,
#     "mdr_out": 3,
#     "traffic": '67b42951-1ef0-4f05-9a0c-fd47fb910fca',
#     "ftd": False
# }
# response = requests.post(url, json=data, headers=headers)
# print(response.text)