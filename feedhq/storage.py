import tempfile
import os
import errno

from django.conf import settings
from django.core.files import locks
from django.core.files.move import file_move_safe
from django.utils.text import get_valid_filename
from django.core.files.storage import FileSystemStorage


class OverwritingStorage(FileSystemStorage):
    """
    File storage that allows overwriting of stored files.
    """

    def get_available_name(self, name):
        return name

    def _save(self, name, content):
        """
        Lifted partially from django/core/files/storage.py
        """
        full_path = self.path(name)

        directory = os.path.dirname(full_path)
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
        if not os.path.isdir(directory):
            raise IOError("%s exists and is not a directory." % directory)

        # This file has a file path that we can move.
        if hasattr(content, 'temporary_file_path'):
            temp_data_location = content.temporary_file_path()
        else:
            tmp_prefix = "tmp_%s" % (get_valid_filename(name), )
            temp_data_location = tempfile.mktemp(prefix=tmp_prefix,
                                                 dir=self.location)
            try:
                # This is a normal uploadedfile that we can stream.
                # This fun binary flag incantation makes os.open throw an
                # OSError if the file already exists before we open it.
                fd = os.open(temp_data_location,
                             os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | getattr(os, 'O_BINARY', 0))
                locks.lock(fd, locks.LOCK_EX)
                for chunk in content.chunks():
                    os.write(fd, chunk)
                locks.unlock(fd)
                os.close(fd)
            except Exception, e:
                if os.path.exists(temp_data_location):
                    os.remove(temp_data_location)
                raise

        file_move_safe(temp_data_location, full_path, allow_overwrite=True)
        content.close()

        if settings.FILE_UPLOAD_PERMISSIONS is not None:
            os.chmod(full_path, settings.FILE_UPLOAD_PERMISSIONS)
        return name
