from os import listdir, makedirs
from os.path import exists
from argparse import ArgumentParser
from math import ceil

import struct
import csv
import yaml
from pygame import Surface, image


class Main:
    def __init__(self):
        parser = ArgumentParser()
        parser.add_argument("-e", "--extract", choices=["strgs", "fonts"], action="append", default=[])
        parser.add_argument("-r", "--repack", choices=["strgs", "fonts"], action="append", default=[])
        parser.add_argument("-p", "--paks", nargs="*")
        parser.add_argument("-pf", "--paks_folder", default="paks")
        parser.add_argument("-sf", "--strgs_folder", default="extracted/strgs")
        parser.add_argument("-ff", "--fonts_folder", default="extracted/fonts")
        parser.add_argument("-al", "--additional_languages", nargs="+", default=[])
        parser.add_argument("-ol", "--overwrite_languages", default="")
        arguments = parser.parse_args()
        pak_names = [pak_name for pak_name in listdir(arguments.paks_folder)]
        if arguments.paks is not None:
            pak_names = [pak_name for pak_name in pak_names
                         if pak_name.lower() in [argument.lower() for argument in arguments.paks]]
        if arguments.extract == [] and arguments.repack == []:
            parser.print_help()
        for format_ in arguments.extract:
            if format_ == "strgs":
                self.extract_strgs(pak_names, arguments.paks_folder, arguments.strgs_folder,
                                   arguments.additional_languages)
            elif format_ == "fonts":
                self.extract_fonts(pak_names, arguments.paks_folder, arguments.fonts_folder)
        for format_ in arguments.repack:
            if format_ == "strgs":
                strg_pak_names = [pak_name for pak_name in listdir(arguments.strgs_folder)]
                if arguments.paks is not None:
                    strg_pak_names = [pak_name for pak_name in strg_pak_names if pak_name.lower().split(".")[0] in
                                      [argument.lower() for argument in arguments.paks]]
                self.repack_strgs(strg_pak_names, arguments.paks_folder,
                                  arguments.strgs_folder, arguments.overwrite_languages)
            elif format_ == "fonts":
                self.repack_fonts(arguments.paks_folder, arguments.fonts_folder)

    @staticmethod
    def extract_strgs(pak_names, paks_folder, strgs_folder, additional_languages):
        strg_names = {pak_name: [file_name for file_name in listdir(f"{paks_folder}/{pak_name}")
                      if file_name.endswith(".STRG")] for pak_name in pak_names}
        strgs = {pak_name: [Strg().open_strg(f"{paks_folder}/{pak_name}/{strg_name}")
                 for strg_name in strg_names[pak_name]] for pak_name in strg_names}
        if not exists(strgs_folder):
            makedirs(strgs_folder)
        for pak_name in strgs:
            Strg.save_as_csv(f"{strgs_folder}/{pak_name}.csv", strgs[pak_name], additional_languages)

    @staticmethod
    def repack_strgs(strg_pak_names, paks_folder, strgs_folder, overwrite_languages):
        for path in strg_pak_names:
            [strg.save_as_strg(f"{paks_folder}/{'.'.join(path.split('.')[:-1])}/{strg.id}.STRG") for strg in
             Strg.from_csv(f"{strgs_folder}/{path}", overwrite_languages)]

    @staticmethod
    def extract_fonts(pak_names, paks_folder, fonts_folder):
        font_paths = [(pak, file) for pak in pak_names for file in listdir(f"{paks_folder}/{pak}")
                      if file.endswith(".FONT")]
        fonts = {}
        for path in font_paths:
            font_id = path[1]
            if font_id not in fonts:
                fonts[font_id] = Font().from_font_txtr(f"{paks_folder}/{path[0]}/{path[1]}")
            fonts[font_id].usings.append(path[0])
        for font in fonts.values():
            path = f"{fonts_folder}/{font.font_name} {font.font_size} {font.id}"
            if not exists(path):
                makedirs(path)
            font.save_as_yaml_pngs(path)

    @staticmethod
    def repack_fonts(paks_folder, fonts_folder):
        fonts = [Font().from_yaml_pngs(f"{fonts_folder}/{path}") for path in listdir(fonts_folder)]
        for font in fonts:
            font.save_as_font_strg(paks_folder)


class FileReader:
    def __init__(self, bytes_):
        self.offset = 0
        self.bytes = bytes_

    def read(self, format_):
        size = struct.calcsize(format_)
        data = struct.unpack(format_, self.bytes[self.offset: self.offset + size])
        self.offset += size
        return data

    def iter_read(self, format_, count):
        size = struct.calcsize(format_) * count
        data = struct.iter_unpack(format_, self.bytes[self.offset: self.offset + size])
        self.offset += size
        return [i for i in data]

    def read_utf16be(self):
        end_offset = self.bytes.find(b"\x00\x00", self.offset)
        while (end_offset - self.offset) % 2 != 0 and end_offset != -1:
            self.offset = self.bytes.find(b"\x00\x00", end_offset)
        string = self.bytes[self.offset: end_offset].decode("UTF-16BE")
        self.offset = end_offset
        return string

    def read_ansi(self):
        end_offset = self.bytes.find(b"\x00", self.offset)
        string = self.bytes[self.offset: end_offset].decode("ANSI")
        self.offset = end_offset + 1
        return string

    def read_nibbles(self, count):
        if count % 2 != 0:
            raise Exception("File reader can't read odd number of nibbles")
        nibbles = []
        for byte, in self.iter_read(">B", count // 2):
            nibbles.append(byte >> 4)
            nibbles.append(byte & 15)
        return nibbles


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
            raise Exception(f"Wrong MAGIC in file {path}. File MAGIC is {magic} and required to be {self.MAGIC}.")
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
    def from_csv(path, overwrite_languages):
        with open(path, "rt", encoding="UTF-8") as file:
            raw_data = [i for i in csv.reader(file, dialect="unix")]
        overwrite_languages = {languages.split(">")[0]: languages.split(">")[1]
                               for languages in overwrite_languages.split() if languages != []}
        version = int(raw_data[0][0].split("=")[-1])
        raw_data = raw_data[1:]
        strgs = []
        languages = None
        for row_index, row in enumerate(raw_data[: -2]):
            if Strg._is_row_empty(raw_data[row_index - 1]):
                languages = Strg._rip_empty_languages(row[1:])
                strgs.append(Strg(row[0], version))
                strgs[-1].strings = {language: [] for language in languages if language not in overwrite_languages}
            elif not Strg._is_row_empty(row):
                for column_index, cell in enumerate(row[1: len(languages) + 1]):
                    language = languages[column_index]
                    if language in overwrite_languages:
                        strgs[-1].strings[overwrite_languages[language]].append(cell)
                    elif language not in overwrite_languages.values():
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
                raise Exception(f"({self.id}) Strings count in different languages are not the same")
        return count


class Font:
    MAGIC = 0x464F4E54

    def __init__(self):
        self.usings = []

    def from_font_txtr(self, path):
        self.pak_path = "/".join(path.split("/")[: -1])
        self.file_name = path.split("/")[-1]
        self.id = ".".join(self.file_name.split('.')[:-1]).upper()
        with open(path, "rb") as file:
            reader = FileReader(file.read())
        magic, self.version = reader.read(">LL")
        if magic != self.MAGIC:
            raise Exception(f"Wrong MAGIC in file {path}. File MAGIC is {magic} and required to be {self.MAGIC}.")
        if self.version == 4:
            (self.width, self.height, self.vertical_offset, self.line_margin,
                self.tmp1, self.tmp2, self.tmp3, self.font_size) = reader.read(">4L2?2L")
            self.font_name = reader.read_ansi()
            texture_id, self.texture_mode, glyph_count = reader.read(">3L")
            self.texture_id = hex(texture_id)[2:]
            self.glyphs = [FontGlyph().from_data(*i[:-1]) for i in reader.iter_read(">H4f7BH", glyph_count)]
            self.kerning = {self.decode_character(i[0]) + self.decode_character(i[1]): i[2]
                            for i in reader.iter_read(">2Hl", reader.read(">L")[0])}
            self.texture = FontTxtr().from_txtr(f"{self.pak_path}/{self.texture_id}.TXTR")
        else:
            raise Exception("Unsupported version")
        return self

    def from_yaml_pngs(self, folder):
        with open(f"{folder}/Font.yaml", "rt", encoding="UTF-8") as file:
            dict_ = yaml.safe_load(file)
            self.texture = FontTxtr().from_pngs(folder, dict_["Texture palette"])
            self.from_dict(dict_, self.texture.size)
        return self

    def save_as_font_strg(self, paks_folder):
        if self.version == 4:
            buffer = struct.pack(">LL4L2?2L", self.MAGIC, self.version, self.width, self.height, self.vertical_offset,
                                 self.line_margin, self.tmp1, self.tmp2, self.tmp3, self.font_size)
            buffer += self.font_name.encode("ANSI") + b"\x00"
            buffer += struct.pack(">LLL", int(self.texture_id, 16), self.texture_mode, len(self.glyphs))
            for glyph in self.glyphs:
                buffer += glyph.get_bytes(self.kerning, self.version)
            buffer += struct.pack(">L", len(self.kerning))
            for character_pair in self.kerning:
                buffer += self.encode_character(character_pair) + struct.pack(">l", self.kerning[character_pair])
        else:
            raise Exception("Unsupported version")
        self.texture.save_as_txtr([f"{paks_folder}/{using}/{self.texture_id}.TXTR" for using in self.usings])
        for using in self.usings:
            with open(f"{paks_folder}/{using}/{self.id}.FONT", "wb") as file:
                file.write(buffer)

    def save_as_yaml_pngs(self, folder):
        with open(f"{folder}/Font.yaml", "wt", encoding="UTF-8") as file:
            yaml.dump(self.get_dict(), file, sort_keys=False, allow_unicode=True)
            self.texture.save_as_pngs(folder)

    def from_dict(self, dict_, texture_size):
        self.id = dict_["ID"]
        self.version = dict_["Version"]
        self.usings = dict_["Usings"]
        self.width = dict_["Width"]
        self.height = dict_["Height"]
        self.vertical_offset = dict_["Vertical offset"]
        self.line_margin = dict_["Line margin"]
        self.tmp1 = dict_["?"]
        self.tmp2 = dict_["??"]
        self.tmp3 = dict_["???"]
        self.font_size = dict_["Font size"]
        self.font_name = dict_["Font name"]
        self.texture_id = dict_["Texture id"]
        self.texture_mode = dict_["Texture mode"]
        self.glyphs = [FontGlyph().from_dict(character, glyph_dict, texture_size)
                       for character, glyph_dict in dict_["Glyphs"].items()]
        self.kerning = {pair: dict_["Kerning"][pair] for pair in dict_["Kerning"] if dict_["Kerning"][pair] != 0}

    def get_dict(self):
        return {"ID":              self.id,
                "Version":         self.version,
                "Usings":          self.usings,
                "Width":           self.width,
                "Height":          self.height,
                "Vertical offset": self.vertical_offset,
                "Line margin":     self.line_margin,
                "?":               self.tmp1,
                "??":              self.tmp2,
                "???":             self.tmp3,
                "Font size":       self.font_size,
                "Font name":       self.font_name,
                "Texture id":      self.texture_id,
                "Texture mode":    self.texture_mode,
                "Texture palette": self.texture.palette_colors,
                "Glyphs":          {glyph.character: glyph.get_dict(self.texture.size) for glyph in self.glyphs},
                "Kerning":        {pair: self.kerning[pair] for pair in self.kerning if self.kerning[pair] != 0}}

    @staticmethod
    def decode_character(character):
        return character.to_bytes(2, "big").decode("UTF-16BE")

    @staticmethod
    def encode_character(character):
        return character.encode("UTF-16BE")


class FontGlyph:
    def from_data(self, character, left, top, right, bottom, layer_index, left_padding, print_head_advance,
                  right_padding, width, height, vertical_offset):
        self.character = Font.decode_character(character) if type(character) == int else character
        self.top_left_uv = [left, top]
        self.bottom_right_uv = [right, bottom]
        self.layer_index = layer_index
        self.padding = [left_padding, right_padding]
        self.print_head_advance = print_head_advance
        self.size = [width, height]
        self.vertical_offset = vertical_offset
        return self

    def from_dict(self, character, dict_, texture_size):
        top_left_uv = self.translate_xy_to_uv([dict_["Left"], dict_["Top"]], texture_size)
        bottom_right_uv = self.translate_xy_to_uv([dict_["Right"], dict_["Bottom"]], texture_size)
        return self.from_data(character,
                              top_left_uv[0],
                              top_left_uv[1],
                              bottom_right_uv[0],
                              bottom_right_uv[1],
                              dict_["Layer"],
                              dict_["Left padding"],
                              dict_["Print head advance"],
                              dict_["Right padding"],
                              dict_["Width"],
                              dict_["Height"],
                              dict_["Vertical offset"])

    def get_bytes(self, kerning, version):
        buffer = self.character.encode("UTF-16BE")
        buffer += struct.pack(">4f", self.top_left_uv[0], self.top_left_uv[1],
                              self.bottom_right_uv[0], self.bottom_right_uv[1])
        if version >= 4:
            buffer += struct.pack(">B", self.layer_index)
        buffer += struct.pack(">6BH", self.padding[0], self.print_head_advance, self.padding[1], self.size[0],
                              self.size[1], self.vertical_offset, self.get_kerning_start_index(self.character, kerning))
        return buffer

    def get_dict(self, texture_size):
        top_left_xy = self.translate_uv_to_xy(self.top_left_uv, texture_size)
        bottom_right_xy = self.translate_uv_to_xy(self.bottom_right_uv, texture_size)
        return {"Left":               top_left_xy[0],
                "Right":              bottom_right_xy[0],
                "Top":                top_left_xy[1],
                "Bottom":             bottom_right_xy[1],
                "Layer":              self.layer_index,
                "Left padding":       self.padding[0],
                "Right padding":      self.padding[1],
                "Print head advance": self.print_head_advance,
                "Width":              self.size[0],
                "Height":             self.size[1],
                "Vertical offset":    self.vertical_offset}

    @staticmethod
    def translate_uv_to_xy(uv, texture_size):
        return [uv[0] * texture_size[0], uv[1] * texture_size[1]]

    @staticmethod
    def translate_xy_to_uv(xy, texture_size):
        return [xy[0] / texture_size[0], xy[1] / texture_size[1]]

    @staticmethod
    def get_kerning_start_index(character, kerning):
        try:
            return [kern[0] for kern in kerning].index(character)
        except ValueError:
            return len(kerning) + 1


class FontTxtr:
    BLOCK_SIZE = [8, 8]

    def from_txtr(self, path):
        with open(path, "rb") as file:
            reader = FileReader(file.read())
        self.image_format, width, height, mipmap_count, palette_format = reader.read(">L2H2L")
        self.size = [width, height]
        if self.image_format != 4:
            raise Exception(f"Wrong/unsupported texture format in file {path}")
        palette_width, palette_height = reader.read(">2H")
        self.palette_colors = [int(i[0]) for i in reader.iter_read(">H", palette_width * palette_height)]
        blocks_in_row_count = ceil(self.size[0] / self.BLOCK_SIZE[0])
        self.images = [Surface(self.size, 0, 8) for _ in range(4)]
        pixels_count = (blocks_in_row_count * ceil(self.size[1] / self.BLOCK_SIZE[1]) *
                        self.BLOCK_SIZE[0] * self.BLOCK_SIZE[1])
        for pixel_index, pixel in enumerate(reader.read_nibbles(pixels_count)):
            for i, image in enumerate(self.images):
                if (pixel >> i) & 1:
                    image.set_at(self.translate_coords(pixel_index, blocks_in_row_count), "White")
        return self

    def from_pngs(self, folder, palette):
        self.images = [image.load(f"{folder}/Layer {i}.png") for i in range(4)]
        self.size = self.images[0].get_size()
        self.palette_colors = palette
        return self

    def save_as_txtr(self, paths):
        buffer = struct.pack(">L2H2L2H", 4, self.size[0], self.size[1], 1, 2, 1, 16)
        for color in self.palette_colors:
            buffer += struct.pack(">H", color)
        blocks_in_row_count = ceil(self.size[0] / self.BLOCK_SIZE[0])
        pixels_count = (blocks_in_row_count * ceil(self.size[1] / self.BLOCK_SIZE[1]) *
                        self.BLOCK_SIZE[0] * self.BLOCK_SIZE[1])
        pixels = []
        for pixel_index in range(pixels_count):
            bits = []
            for image_index, image in enumerate(self.images):
                bits.append(image.get_at(self.translate_coords(pixel_index, blocks_in_row_count)).r > 127)
            pixels.append(self.bits_to_int(bits))
        for i in range(0, len(pixels), 2):
            buffer += ((pixels[i] << 4) + pixels[i + 1]).to_bytes(1, "big")
        for path in paths:
            with open(path, "wb") as file:
                file.write(buffer)

    def save_as_pngs(self, path):
        for i, layer in enumerate(self.images):
            image.save(layer, f"{path}/Layer {i}.png")

    def translate_coords(self, byte_offset, blocks_in_row_count):
        block_index = byte_offset // 64
        pixel_in_block_index = byte_offset % 64
        block_coords = [block_index % blocks_in_row_count, block_index // blocks_in_row_count]
        pixel_in_block_coords = [pixel_in_block_index % 8, pixel_in_block_index // 8]
        return [block_coords[0] * self.BLOCK_SIZE[0] + pixel_in_block_coords[0],
                block_coords[1] * self.BLOCK_SIZE[1] + pixel_in_block_coords[1]]

    @staticmethod
    def bits_to_int(bits):
        return sum(map(lambda x: x[1] << x[0], enumerate(bits)))


if __name__ == "__main__":
    Main()
