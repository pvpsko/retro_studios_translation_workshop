from os import listdir
from argparse import ArgumentParser
import struct
import csv


class FileReader:
    def __init__(self, raw_bytes):
        self.offset = 0
        self.raw_bytes = raw_bytes

    def read(self, format_):
        size = struct.calcsize(format_)
        readed_data = struct.unpack(format_, self.raw_bytes[self.offset: self.offset + size])
        self.offset += size
        return readed_data

    def iter_read(self, format_, count):
        size = struct.calcsize(format_) * count
        readed_data = struct.iter_unpack(format_, self.raw_bytes[self.offset: self.offset + size])
        self.offset += size
        return [i for i in readed_data]

    def read_utf16be(self):
        end_offset = self.raw_bytes.find(b"\x00\x00", self.offset)
        while (end_offset - self.offset) % 2 != 0 and end_offset != -1:
            self.offset = self.raw_bytes.find(b"\x00\x00", end_offset)
        string = self.raw_bytes[self.offset: end_offset].decode("UTF-16BE")
        self.offset = end_offset
        return string


class Strg:
    MAGIC = 0x87654321

    def __init__(self, id_=None, version=None):
        self.version = version
        self.id = id_
        self.strings = {}

    def open_strg(self, path):
        self.id = path.split("/")[-1].split(".")[0]
        with open(path, "rb") as file:
            reader = FileReader(file.read())
        magic, self.version = reader.read(">LL")
        if magic != self.MAGIC:
            raise Exception(f"Wrong MAGIC in file {path}")
        if self.version > 0:
            raise Exception(f"Unsupported VERSION in file {path}")
        language_count, string_count = reader.read(">LL")
        language_table = {}
        for language_id, language_offset in reader.iter_read(">4sL", language_count):
            language_table[language_id] = language_offset
        strings_start_offset = reader.offset
        for language in language_table:
            reader.offset = strings_start_offset + language_table[language] + 4
            language_strings_offset = reader.offset
            string_offsets = reader.iter_read(">L", string_count)
            self.strings[language] = []
            for string_offset in string_offsets:
                reader.offset = language_strings_offset + string_offset[0]
                self.strings[language].append(reader.read_utf16be())
        return self

    def save_as_strg(self, path):
        if self.version > 0:
            raise Exception(f"Unsupported VERSION")
        header = struct.pack(">LLLL", self.MAGIC, self.version, len(self.strings), self.strings_count)
        language_table = b""
        string_table = b""
        language_offset = 0
        for language in self.strings:
            string_offsets = b""
            strings = b""
            string_offset = len(self.strings[language]) * 4
            for string in [string.encode("UTF-16BE") + b"\x00\x00" for string in self.strings[language]]:
                string_offsets += struct.pack(">L", string_offset)
                strings += string
                string_offset += len(string)
            string_table_size = len(string_offsets) + len(strings)
            string_table += struct.pack(">L", string_table_size) + string_offsets + strings
            language_table += language.encode("ASCII") + struct.pack(">L", language_offset)
            language_offset += 4 + string_table_size
        buffer = header + language_table + string_table
        with open(path, "wb") as file:
            file.write(buffer + b"\xFF" * (32 - len(buffer) % 32))
    
    @staticmethod
    def open_csv(file, language_overwrite):
        raw_data = [i for i in csv.reader(file, dialect="unix")]
        language_overwrite = {languages.split(">")[0]: languages.split(">")[1] for languages in language_overwrite.split() if languages != []}
        version = int(raw_data[0][0].split("=")[-1])
        raw_data = raw_data[1:]
        strgs = []
        for row_index, row in enumerate(raw_data[: -2]):
            if Strg._is_row_empty(raw_data[row_index - 1]):
                languages = Strg._rip_empty_languages(row[1:])
                strgs.append(Strg(row[0], version))
                strgs[-1].strings = {language: [] for language in languages if language not in language_overwrite}
            elif not Strg._is_row_empty(row):
                for column_index, cell in enumerate(row[1: len(languages) + 1]):
                    language = languages[column_index]
                    if language in language_overwrite:
                        strgs[-1].strings[language_overwrite[language]].append(cell)
                    elif language not in language_overwrite.values():
                        strgs[-1].strings[language].append(cell)
        return strgs

    @staticmethod
    def _rip_empty_languages(langs):
        return [lang for lang in langs if lang != ""]

    @staticmethod
    def _is_row_empty(row):
        for i in row:
            if i != "":
                return False
        return True

    @staticmethod
    def save_as_csv(path, strgs, additional_langs=None):
        if additional_langs is None:
            additional_langs = []
        if len(strgs) == 0:
            return
        with open(path, 'w', encoding="UTF-8") as file:
            writer = csv.writer(file, dialect='unix')
            writer.writerow([f"Version={strgs[0].version}"])
            for strg in strgs:
                writer.writerow([])
                writer.writerow([strg.id] + [str(lang)[2:-1] for lang in strg.strings] + additional_langs)
                for string in range(strg.strings_count):
                    writer.writerow([string] + [strg.strings[language][string] for language in strg.strings])

    @property
    def strings_count(self):
        count = None
        for language in self.strings:
            if count is None:
                count = len(self.strings[language])
            elif count != len(self.strings[language]):
                raise Exception(f"({self.id}) Strings count in diferrent languages are not the same")
        return count


class Dsp:
    def __init__(self):
        ...


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-e", "--extract", choices=["strgs"], action="append", default=[])
    parser.add_argument("-r", "--repack", choices=["strgs"], action="append", default=[])
    parser.add_argument("-p", "--paks", nargs="*")
    parser.add_argument("-pf", "--paks_foulder", default="paks")
    parser.add_argument("-sf", "--strgs_foulder", default="strgs")
    parser.add_argument("-al", "--additional_languages", nargs="+", default=[])
    parser.add_argument("-lo", "--language_overwrite", default="")
    arguments = parser.parse_args()
    print(arguments)
    if arguments.extract == [] and arguments.repack == []:
        parser.print_help()
    for format_ in arguments.extract:
        if format_ == "strgs":
            if arguments.paks is not None:
                pak_names = [pak_name for pak_name in listdir(arguments.paks_foulder) if pak_name.lower() in [argument.lower() for argument in arguments.paks]]
            else:
                pak_names = [pak_name for pak_name in listdir(arguments.paks_foulder)]
            strg_names = {pak_name: [file_name for file_name in listdir(f"{arguments.paks_foulder}/{pak_name}") if file_name.endswith(".STRG")] for pak_name in pak_names}
            strgs = {pak_name: [Strg().open_strg(f"{arguments.paks_foulder}/{pak_name}/{strg_name}") for strg_name in strg_names[pak_name]] for pak_name in strg_names}
            [Strg.save_as_csv(f"{arguments.strgs_foulder}/{pak_name}.csv", strgs[pak_name], arguments.additional_languages) for pak_name in strgs]
    for format_ in arguments.repack:
        if format_ == "strgs":
            for path in listdir(arguments.strgs_foulder):
                with open(f"{arguments.strgs_foulder}/{path}", "rt", encoding="UTF-8") as file:
                    [strg.save_as_strg(f"{arguments.paks_foulder}/{'.'.join(path.split('.')[:-1])}/{strg.id}.STRG") for strg in Strg.open_csv(file, arguments.language_overwrite)]
