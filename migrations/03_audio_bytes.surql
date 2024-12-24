-- First remove the old audio column if it exists
REMOVE FIELD IF EXISTS audio ON TABLE chapter;

-- Add new audio columns to schema
DEFINE FIELD audio_data ON TABLE chapter TYPE option<bytes> PERMISSIONS FULL;
DEFINE FIELD audio_mime ON TABLE chapter TYPE option<string> PERMISSIONS FULL; 