input = request.form.get("request")

spotify_schema = {
    "type": "object",
    "properties": {
        "artist": {"type": "string"},
        "action": {"type": "string", "enum": ["play", "pause", "skip"]},
    },
    "required": ["artist", "action"],
    "additionalProperties": False,
}

response = client.responses.create(
model="gpt-5",
input=input,
text={
    "format": {
        "type": "json_schema",
        "name": "spotify_command",
        "strict": True,
        "schema": spotify_schema
    }
})


class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., min_length=10)
    API_KEY: SecretStr
    DEBUG: bool = False

    model_config = SettingConfigDict(env_file=".env")

try:
    settings = Settings()
    print("Environment Variables Validated.")
except Exception as e:
    print("Boot Error: {e}")
