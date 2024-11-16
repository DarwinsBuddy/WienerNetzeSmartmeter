import sqlite3


def purge(database:str, days: int, sensor_id: str):
    conn = sqlite3.connect(database)
    cursor = conn.cursor()

    query = f"""
    DELETE FROM statistics
    WHERE metadata_id IN (
        SELECT id FROM statistics_meta WHERE statistic_id = '{sensor_id}'
    )
    AND start_ts >= strftime('%s', 'now', '-{days} days');
    """

    # Execute the query
    cursor.execute(query)

    # Commit the changes and close the connection
    conn.commit()
    conn.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Purge the last x days of data from the statistics table')
    parser.add_argument('-db', '--database', type=str, help='Path to the SQLite database', default="home-assistant_v2.db")
    parser.add_argument('-d', '--days', type=int, help='Number of days to keep', default=2)
    parser.add_argument('-s', '--sensor', type=str, help='Name in the statistics_meta table', default="sensor.at00100000000000000010000XXXXXXX_statistics")
    args = parser.parse_args()
    purge(args.database, args.days, args.sensor)
