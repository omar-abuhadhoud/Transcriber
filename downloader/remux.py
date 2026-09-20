"""Dropping the video track without re-encoding anything.

Only YouTube reliably offers an audio-only stream. Instagram, Facebook and TikTok hand
out a progressive MP4 with the video muxed in, so "download the audio" there means
downloading the file and then throwing the picture away.

This does that by copying the audio packets into a new container untouched -- no
decode, no encode. It takes well under a second on a reel, costs nothing in quality,
and needs no ffmpeg binary, because PyAV (already a dependency, used to decode audio
for transcription) carries its own.

Failure is never fatal. Transcription decodes with PyAV too, and PyAV is perfectly
happy reading the audio out of an MP4, so the worst case of a failed remux is a larger
file on disk.
"""

import os

# Audio codec -> (container extension, PyAV format name). A codec missing from here is
# left in whatever container it arrived in rather than guessed at, because muxing a
# codec into a container that cannot hold it produces a file nothing will open.
CONTAINERS = {
    "aac": (".m4a", "mp4"),
    "alac": (".m4a", "mp4"),
    "mp3": (".mp3", "mp3"),
    "opus": (".opus", "ogg"),
    "vorbis": (".ogg", "ogg"),
    "flac": (".flac", "flac"),
    "pcm_s16le": (".wav", "wav"),
}


def audio_only_path(source_path):
    """Copy `source_path`'s audio into its own file and delete the original.

    Returns the new path, or `source_path` unchanged when there is nothing to gain or
    the copy could not be made.
    """
    import av

    try:
        with av.open(source_path, mode="r", metadata_errors="ignore") as container:
            if not container.streams.audio:
                # Nothing to extract. Transcription will fail on this later and say so
                # properly; silently producing an empty file would be worse.
                return source_path
            if not container.streams.video:
                # Already audio-only, which is the YouTube path.
                return source_path

            codec = container.streams.audio[0].codec_context.name
    except Exception:
        return source_path

    target = CONTAINERS.get(codec)
    if target is None:
        return source_path

    extension, format_name = target
    stem, current_extension = os.path.splitext(source_path)
    if current_extension.lower() == extension:
        # Same extension, video inside: remux in place through a temporary file.
        destination = stem + ".audio" + extension
        rename_over = source_path
    else:
        destination = stem + extension
        rename_over = None

    try:
        _copy_audio(source_path, destination, format_name)
    except Exception:
        # A half-written container is worse than no container.
        _discard(destination)
        return source_path

    # Only now is the original expendable. Deleting it first would risk losing the
    # download outright if the copy turned out to be unusable.
    _discard(source_path)

    if rename_over is not None:
        try:
            os.replace(destination, rename_over)
            return rename_over
        except OSError:
            return destination

    return destination


def _copy_audio(source_path, destination, format_name):
    import av

    with av.open(source_path, mode="r", metadata_errors="ignore") as source:
        stream = source.streams.audio[0]

        with av.open(destination, mode="w", format=format_name) as output:
            out_stream = output.add_stream_from_template(stream)

            for packet in source.demux(stream):
                # The demuxer emits a final empty packet to signal end of stream; it
                # has no timestamp and muxing it raises.
                if packet.dts is None:
                    continue
                packet.stream = out_stream
                output.mux(packet)


def _discard(path):
    try:
        os.remove(path)
    except OSError:
        pass
