from airflow.sdk import dag, task
import pendulum


@dag(
    dag_id="kutuse_transform_pipeline",
    schedule="0 9 * * 5",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    tags=["kutus", "transform"],
)
def kutuse_transform_pipeline():

    @task()
    def run_transforms():
        import sys
        sys.path.insert(0, "/opt/airflow/transform")
        sys.path.insert(0, "/opt/airflow/transform/tables")
        from run_transforms import run_all
        run_all()

    run_transforms()


kutuse_transform_pipeline()