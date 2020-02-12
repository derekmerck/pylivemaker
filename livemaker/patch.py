# -*- coding: utf-8
#
# Copyright (C) 2019 Peter Rowlands <peter@pmrowla.com>
# Copyright (C) 2014 tinfoil <https://bitbucket.org/tinfoil/>
#
# This file is a part of pylivemaker.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
"""pylivemaker patcher."""

import logging
import os
import os.path
import sys
import tempfile
import shutil
from pathlib import Path, PureWindowsPath

import click

from livemaker import LMArchive, LMCompressType
from livemaker.exceptions import LiveMakerException


log = logging.getLogger(__name__)
fh = logging.FileHandler('patch.log')
fh.setLevel(logging.INFO)
log.addHandler(fh)


@click.command()
# @lmlsb.option('-r', '--recursive', is_flag=True, default=False)
@click.argument('archive_file', required=True, type=click.Path(exists=True, dir_okay=False))
@click.argument('patched_lsb', required=True, type=click.Path(exists=True, dir_okay=False))
@click.option('--split', is_flag=True, default=False,
              help='Generate a split data archive.')
@click.option('--no-backup', is_flag=True, default=False,
              help='Do not generate backup of original archive file(s).')
@click.option('-f', '--force', is_flag=True, default=False,
              help='Overwrite any existing files instead of erroring out.')
def lmpatch(archive_file, patched_lsb, split, no_backup, force):
    """Patch a LiveMaker game.

    Any existing version of patched_lsb will be replaced in the specified
    LiveMaker archive. If a file with the same name as patched_lsb does
    not already exist, this will do nothing.

    If file extension for archive_file is ".ext", or if archive_file is not
    an excutable and the --split option is specified,
    a split archive will be generated.

    A backup copy of the old archive file(s) will also be created unless the
    --no-backup option is specified.

    """
    archive_path = Path(archive_file).resolve()
    archive_dir = archive_path.parent
    archive_name = archive_path.name

    try:
        orig_lm = LMArchive(archive_path)
    except LiveMakerException as e:
        log.error(e)
        return

    if orig_lm.is_exe:
        fd, tmp_exe = tempfile.mkstemp()
        fp = os.fdopen(fd, 'wb')
        fp.write(orig_lm.read_exe())
        fp.close()
    else:
        if orig_lm.is_split:
            split = True
        tmp_exe = None

    if not no_backup:
        backup_paths = {archive_path: Path('{}.bak'.format(archive_path))}
        if orig_lm.is_split:
            for p in orig_lm._split_files:
                backup_paths[Path(p)] = Path('{}.bak'.format(p))
        for p in backup_paths.values():
            if p.exists():
                if force:
                    print('{} will be overwritten'.format(p))
                else:
                    sys.exit('{} already exists'.format(p))

    lsb_path = PureWindowsPath(patched_lsb)
    try:
        tmpdir = tempfile.mkdtemp()
        tmpdir_path = Path(tmpdir)
        log.info('Using temp directory {}'.format(tmpdir_path))
        print('Generating new archive contents...')
        with LMArchive(name=tmpdir_path.joinpath(archive_name), mode='w', version=orig_lm.version, exe=tmp_exe,
                       split=split) as new_lm:

            def bar_show(item):
                width, _ = click.get_terminal_size()
                width //= 4
                name = item.name if item is not None else ''
                if len(name) > width:
                    name = ''.join(['...', name[-width:]])
                return name

            # patch
            with click.progressbar(orig_lm.infolist(), item_show_func=bar_show) as bar:
                for info in bar:
                    if info.path == lsb_path:
                        # replace existing with patch version
                        #
                        # TODO: support writing encrypted files
                        if info.compress_type == LMCompressType.ENCRYPTED:
                            compress_type = LMCompressType.NONE
                        elif info.compress_type == LMCompressType.ENCRYPTED_ZLIB:
                            compress_type = LMCompressType.ZLIB
                        else:
                            compress_type = info.compress_type
                        new_lm.write(lsb_path, compress_type=compress_type, unk1=info.unk1)
                        log.info('patched {}'.format(lsb_path))
                        # print('patched')
                    else:
                        # copy original version
                        data = orig_lm.read(info, decompress=False)
                        new_lm.writebytes(info, data)
                        log.info('copied {}'.format(lsb_path))
                    # print(info.name)
        orig_lm.close()

        # copy temp dir contents to output path then remove the temp dir
        # this operation needs to be a copy instead of rename (move)
        # in case windows system temp directory is on a different
        # logical drive than the output path
        print('Writing new archive files...')
        for root, dirs, files in os.walk(tmpdir_path):
            for name in files:
                tmp_p = Path(root).joinpath(name)
                orig_p = archive_dir.joinpath(name)
                if orig_p.exists() and not no_backup:
                    orig_p.rename(backup_paths[orig_p])
                shutil.copy(tmp_p, archive_dir)
    except Exception as e:
        log.error(e)

        raise e
    finally:
        if tmp_exe is not None:
            Path(tmp_exe).unlink()

        print('Cleaning up temporary files...')
        if tmpdir_path:
            for root, dirs, files in os.walk(tmpdir_path):
                for name in files:
                    p = Path(root).joinpath(name)
                    p.unlink()
            tmpdir_path.rmdir()


if __name__ == '__main__':
    lmpatch()
