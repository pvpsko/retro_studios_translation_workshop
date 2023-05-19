import time
from os import listdir, makedirs
from os.path import exists
from argparse import ArgumentParser
from math import ceil

import zlib
import struct
import csv
import yaml
from pygame import Surface, image


class Main:
    def __init__(self):
        start_time = time.time()
        parser = ArgumentParser()
        parser.add_argument("-e", "--extract", choices=["strgs", "fonts", "paks"], action="append", default=[])
        parser.add_argument("-r", "--repack", choices=["strgs", "fonts", "paks"], action="append", default=[])
        parser.add_argument("-gf", "--game_folder", default="MetroidPrime/files")
        parser.add_argument("-mgf", "--modded_game_folder", default="MetroidPrimeModded/files")
        parser.add_argument("-rf", "--resource_folder", default="resources")
        parser.add_argument("-sp", "--strgs_path", default="extracted/strgs.csv")
        parser.add_argument("-ff", "--fonts_folder", default="extracted/fonts")
        parser.add_argument("-al", "--additional_languages", nargs="+", default=[])
        parser.add_argument("-ol", "--overwrite_languages", nargs="+", default=[])
        arguments = parser.parse_args()
        if arguments.extract == [] and arguments.repack == []:
            parser.print_help()
        for format_ in arguments.extract:
            if format_ == "strgs":
                self.extract_strgs(arguments.resource_folder, arguments.strgs_path, arguments.additional_languages)
            elif format_ == "fonts":
                self.extract_fonts(arguments.resource_folder, arguments.fonts_folder)
            elif format_ == "paks":
                self.extract_paks(arguments.game_folder, arguments.resource_folder)
        for format_ in arguments.repack:
            if format_ == "strgs":
                self.repack_strgs(arguments.resource_folder, arguments.strgs_path, arguments.overwrite_languages)
            elif format_ == "fonts":
                self.repack_fonts(arguments.resource_folder, arguments.fonts_folder)
            elif format_ == "paks":
                self.repack_paks(arguments.resource_folder, arguments.modded_game_folder)
        print(f"Done in {round(time.time() - start_time, 3)} seconds")

    @staticmethod
    def extract_paks(game_files_folder, resource_folder):
        resource_reader = AssetReader(resource_folder)
        for pak in [file[:file.find(".")] for file in listdir(game_files_folder) if file.upper().endswith(".PAK")]:
            start_time = time.time()
            print(f"Extracting pak {pak}", end="", flush=True)
            Pak().from_pak(game_files_folder, pak, resource_reader).save_as_files_config(resource_folder)
            print(f" (Done in {round(time.time() - start_time, 3)} seconds)")

    @staticmethod
    def repack_paks(resource_folder, modded_game_folder):
        resource_reader = AssetReader(f"{resource_folder}/files")
        for pak_config_name in [file for file in listdir(resource_folder) if file.lower().endswith(".yaml")]:
            start_time = time.time()
            print(f"Repacking pak {pak_config_name[:pak_config_name.lower().find('.yaml')]}", end="", flush=True)
            with open(f"{resource_folder}/{pak_config_name}", "rb") as file:
                pak_config = yaml.safe_load(file)
            Pak().from_files_config(pak_config_name[:pak_config_name.lower().find(".yaml")],
                                    resource_reader, pak_config).save_as_pak(modded_game_folder, resource_reader)
            print(f" (Done in {round(time.time() - start_time, 3)} seconds)")

    @staticmethod
    def extract_strgs(resource_folder, strgs_path, additional_languages):
        strgs = [Strg().open_strg(f"{resource_folder}/files/{file_name}")
                 for file_name in listdir(f"{resource_folder}/files") if file_name.endswith(".STRG")]
        Strg.save_as_csv(strgs_path, strgs, additional_languages)

    @staticmethod
    def repack_strgs(resources_folder, strgs_path, overwrite_languages):
        for strg in Strg.from_csv(strgs_path, overwrite_languages):
            strg.save_as_strg(f"{resources_folder}/files/{strg.id[2:]}.STRG")

    @staticmethod
    def extract_fonts(resource_folder, fonts_folder):
        font_paths = [file for file in listdir(f"{resource_folder}/files") if file.endswith(".FONT")]
        for path in font_paths:
            font = Font().from_font_txtr(f"{resource_folder}/files/{path}")
            path = f"{fonts_folder}/{font.font_name} {font.font_size} {font.id}"
            if not exists(path):
                makedirs(path)
            font.save_as_yaml_pngs(path)

    @staticmethod
    def repack_fonts(resource_folder, fonts_folder):
        fonts = [Font().from_yaml_pngs(f"{fonts_folder}/{path}") for path in listdir(fonts_folder)]
        for font in fonts:
            font.save_as_font_strg(resource_folder)


class AssetReader:
    def __init__(self, folder=""):
        self.folder = folder
        self.resources = {}

    def get(self, resource_name, align, compress=False):
        data = self.compress_resource(self.resources[resource_name]) if compress else self.resources[resource_name]
        return self.align(data) if align else data

    @staticmethod
    def compress_resource(data):
        return struct.pack(">L", len(data)) + zlib.compress(data)

    @staticmethod
    def decompress_resource(data):
        return zlib.decompress(data[4:])

    @staticmethod
    def align(data, align_byte=b"\xFF", alignment=32):
        return data + (-len(data) % alignment) * align_byte

    def read_file(self, resource_name, is_compressed=False):
        if resource_name not in self.resources:
            with open(f"{self.folder}/{resource_name}", "rb") as file:
                self.resources[resource_name] = file.read()
            if is_compressed:
                self.resources[resource_name] = self.decompress_resource(self.resources[resource_name])

    def set_raw_data(self, resource_name, data, is_compressed):
        if resource_name not in self.resources:
            self.resources[resource_name] = data
            if is_compressed:
                self.resources[resource_name] = self.decompress_resource(self.resources[resource_name])


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


class Pak:
    def from_pak(self, game_folder, pak_name, resource_reader):
        self.name = pak_name
        with open(f"{game_folder}/{pak_name}.pak", "rb") as file:
            reader = FileReader(file.read())
        if reader.read(">2HL") != (3, 5, 0):
            raise Exception(f"Invalid HEADER in pak {pak_name}")
        self.asset_names = {}
        for _ in range(reader.read(">L")[0]):
            asset_type, asset_id, asset_name_length = reader.read(">4s2L")
            asset_name = reader.read(f">{asset_name_length}s")[0].decode("ANSI")
            self.asset_names[asset_name] = f"{hex(asset_id)[2:].upper().rjust(8, '0')}.{asset_type.decode('ANSI')}"
        self.assets = []
        for _ in range(reader.read(">L")[0]):
            compression_flag, asset_type, asset_id, asset_size, asset_offset = reader.read(">L4s3L")
            self.assets.append(
                Asset(asset_type.decode("ANSI"), hex(asset_id)[2:].upper().rjust(8, '0'), compression_flag != 0,
                      resource_reader)
            )
            resource_reader.set_raw_data(self.assets[-1].name, reader.bytes[asset_offset: asset_offset + asset_size],
                                         self.assets[-1].is_compressed)
        return self

    def from_files_config(self, pak_name, resource_reader, pak_config):
        self.name = pak_name
        self.asset_names = pak_config["Names"]
        self.assets = []
        for asset in pak_config["Assets info"]:
            self.assets.append(Asset(asset["Type"], asset["ID"], asset["Compressed"], resource_reader))
            resource_reader.read_file(f"{asset['ID']}.{asset['Type']}")
        return self

    def save_as_pak(self, game_folder, resource_reader):
        header = struct.pack(">2HL", 3, 5, 0)
        name_table = struct.pack(">L", len(self.asset_names))
        for name in self.asset_names:
            id_, type_ = self.asset_names[name].split(".")
            name_table += type_.encode("ANSI") + struct.pack(">LL", int(id_, 16), len(name)) + name.encode("ANSI")
        asset_table = struct.pack(">L", len(self.assets))
        asset_offset = len(header) + len(name_table) + 4 + 20 * len(self.assets)
        assets = b"\x00" * (-asset_offset % 32)
        asset_offset += len(assets)
        for asset in self.assets:
            asset_data = resource_reader.get(asset.name, True, asset.is_compressed)
            asset_table += struct.pack(">L4s3L", 1 if asset.is_compressed else 0, asset.type.encode("ANSI"),
                                       int(asset.id, 16), len(asset_data), asset_offset)
            assets += asset_data
            asset_offset += len(asset_data)
        with open(f"{game_folder}/{self.name}.pak", "wb") as file:
            file.write(header + name_table + asset_table + assets)

    def save_as_files_config(self, folder):
        if not exists(f"{folder}/files"):
            makedirs(f"{folder}/files")
        for asset in self.assets:
            asset.save(f"{folder}/files/{asset.id}.{asset.type}")
        with open(f"{folder}/{self.name}.yaml", "wt") as file:
            file.write(yaml.dump(self.get_info(), sort_keys=False))

    def get_info(self):
        return {
            "Names": self.asset_names,
            "Assets info": [asset.get_info() for asset in self.assets]
        }


class Asset:
    def __init__(self, type_, id_, is_compressed, resource_reader):
        self.type = type_
        self.id = id_
        self.resource_reader = resource_reader
        self.is_compressed = is_compressed
        self.name = f"{self.id}.{self.type}"

    def get_info(self):
        return {
            "ID": self.id,
            "Type": self.type,
            "Compressed": self.is_compressed
        }

    def save(self, path):
        with open(path, "wb") as file:
            file.write(self.resource_reader.get(self.name, False))


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
        magic, self.version = reader.read(">2L")
        if magic != self.MAGIC:
            raise Exception(f"Wrong MAGIC in file {path}. File MAGIC is {magic} and required to be {self.MAGIC}.")
        if self.version > 0:
            raise Exception(f"Unsupported VERSION in file {path}")
        language_count, string_count = reader.read(">2L")
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
        header = struct.pack(">4L", self.MAGIC, self.version, len(self.strings), self.strings_count)
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
            file.write(buffer)
    
    @staticmethod
    def from_csv(path, overwrite_languages):
        with open(path, "rt", encoding="UTF-8") as file:
            raw_data = [i for i in csv.reader(file, dialect="unix")]
        overwrite_languages = {languages.split("2")[0]: languages.split("2")[1] for languages in overwrite_languages}
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
                writer.writerow(["0x" + strg.id] + [str(lang)[2:-1] for lang in strg.strings] + additional_langs)
                for string in range(strg.strings_count):
                    writer.writerow([str(string)] + [strg.strings[language][string] for language in strg.strings] +
                                    ["" for _ in additional_langs])

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

    def from_font_txtr(self, path):
        resource_folder = "/".join(path.split("/")[: -1])
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
            self.texture = FontTxtr().from_txtr(f"{resource_folder}/{self.texture_id}.TXTR")
        else:
            raise Exception("Unsupported version")
        return self

    def from_yaml_pngs(self, folder):
        with open(f"{folder}/Font.yaml", "rt", encoding="UTF-8") as file:
            dict_ = yaml.safe_load(file)
            self.texture = FontTxtr().from_pngs(folder, dict_["Texture palette"])
            self.from_dict(dict_, self.texture.size)
        return self

    def save_as_font_strg(self, resource_folder):
        if self.version == 4:
            buffer = struct.pack(">2L4L2?2L", self.MAGIC, self.version, self.width, self.height, self.vertical_offset,
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
        self.texture.save_as_txtr(f"{resource_folder}/{self.texture_id}.TXTR")
        with open(f"{resource_folder}/{self.id}.FONT", "wb") as file:
            file.write(buffer)

    def save_as_yaml_pngs(self, folder):
        with open(f"{folder}/Font.yaml", "wt", encoding="UTF-8") as file:
            yaml.dump(self.get_dict(), file, sort_keys=False, allow_unicode=True)
            self.texture.save_as_pngs(folder)

    def from_dict(self, dict_, texture_size):
        self.id = dict_["ID"]
        self.version = dict_["Version"]
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

    def save_as_txtr(self, path):
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
