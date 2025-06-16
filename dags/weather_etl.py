from airflow import DAG
from airflow.decorators import task
from airflow.providers.http.hooks.http import HttpHook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from datetime import datetime, timedelta

LATITUDE = 40.7128
LONGITUDE = -74.0060
POSTGRES_CONNECTION_ID = "postgres_default"
API_CONNECTION_ID = "open_meteo_api"

default_arguments = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=1)
}

with DAG(
    dag_id="weather_etl_pipeline",
    default_args=default_arguments,
    schedule='@daily',
    catchup=False,
    start_date=datetime.now() - timedelta(days=1),
    tags=["example"]
) as dag:

    @task
    def fetch_weather_data() -> dict:
        """
        Fetch weather data from the API.
        """
        http_hook = HttpHook(method="GET", http_conn_id=API_CONNECTION_ID)
        response = http_hook.run(
            endpoint=f"v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}&current_weather=true",
        )
        return response.json()
    
    @task
    def transform_weather_data(weather_data: dict) -> dict:
        """
        Transform the weather data to extract relevant fields.
        """
        return {
            "temperature": weather_data["current_weather"]["temperature"],
            "windspeed": weather_data["current_weather"]["windspeed"],
            "weathercode": weather_data["current_weather"]["weathercode"],
            "time": weather_data["current_weather"]["time"],
            "latitude": weather_data["latitude"],
            "longitude": weather_data["longitude"],
            "timezone": weather_data["timezone"]
        }
    
    @task
    def load_weather_data(transformed_weather_data: dict):
        postgresHook = PostgresHook(postgres_conn_id=POSTGRES_CONNECTION_ID)
        connection = postgresHook.get_conn()
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weather_data (
                id SERIAL PRIMARY KEY,
                temperature FLOAT,
                windspeed FLOAT,
                weathercode INT,
                time TIMESTAMP,
                latitude FLOAT,
                longitude FLOAT,
                timezone VARCHAR(50)
            );
        """)

        cursor.execute("""
            INSERT INTO weather_data (temperature, windspeed, weathercode, time, latitude, longitude, timezone)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (
            transformed_weather_data["temperature"],
            transformed_weather_data["windspeed"],
            transformed_weather_data["weathercode"],
            transformed_weather_data["time"],
            transformed_weather_data["latitude"],
            transformed_weather_data["longitude"],
            transformed_weather_data["timezone"]
        ))

        connection.commit()
        cursor.close()
        connection.close()

    # Task chaining
    load_weather_data(transform_weather_data(fetch_weather_data()))
