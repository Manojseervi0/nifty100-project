load:
	python src/etl/loader.py

test:
	python -m pytest

clean:
	del /Q *.db