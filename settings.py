from dotenv import dotenv_values

config = dotenv_values(".env.local")

API_KEY=config["API_KEY"]
BAMBOO_HR_ACCOUNT_TOKEN=config["BAMBOO_HR_ACCOUNT_TOKEN"]
