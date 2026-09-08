# tally

Word counts over plain text. `count_words(text)` returns a dict of lowercase
word to occurrences; words are runs of ASCII letters.

Run the tests with:

    python3 -m unittest discover -s tests -t .

Count the words in a file:

    python3 -m tally path/to/file.txt
