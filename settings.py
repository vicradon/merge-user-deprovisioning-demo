from dotenv import dotenv_values

config = dotenv_values(".env.local")

API_KEY=config["API_KEY"]
BAMBOO_HR_ACCOUNT_TOKEN=config["BAMBOO_HR_ACCOUNT_TOKEN"]
POSTGRES_URL=config["POSTGRES_URL"]
JWT_SECRET=config["JWT_SECRET"]
JWT_ALGORITHM="HS256"