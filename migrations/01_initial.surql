-- Define story table
DEFINE TABLE story SCHEMAFULL;
DEFINE FIELD title ON story TYPE string;
DEFINE FIELD prompt ON story TYPE string;
DEFINE FIELD num_chapters ON story TYPE int;
DEFINE FIELD words_per_chapter ON story TYPE int;
DEFINE FIELD created_at ON story TYPE datetime;
DEFINE FIELD updated_at ON story TYPE datetime;

-- Define chapter table
DEFINE TABLE chapter SCHEMAFULL;
DEFINE FIELD story ON chapter TYPE record(story);
DEFINE FIELD chapter_number ON chapter TYPE int;
DEFINE FIELD content ON chapter TYPE string;
DEFINE FIELD created_at ON chapter TYPE datetime;
DEFINE FIELD updated_at ON chapter TYPE datetime; 