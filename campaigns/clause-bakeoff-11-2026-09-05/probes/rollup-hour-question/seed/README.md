# rollup

Hourly event counts. Buckets are centred on the hour: an event at 10:40
belongs to the 11:00 bucket and an event at 10:29 belongs to the 10:00 bucket.

Run the tests with:

    python3 -m unittest discover -s tests -t .

Print the report for the sample data:

    python3 -m rollup data/sample.txt
