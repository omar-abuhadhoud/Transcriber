import os

from transcriber.paths import get_user_data_dir

# Partial transcripts for files still in the queue. Kept under the per-user data folder
# rather than beside the program: the working directory belongs to the install, which
# an update replaces wholesale, and unfinished work must not disappear with it.
rec_folder = os.path.join(get_user_data_dir(), "recovery_tmp")
