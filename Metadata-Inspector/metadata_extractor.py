from __future__ import annotations

import base64
import csv
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, ImageCms, IptcImagePlugin

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

try:
    from PIL.ExifTags import IFD
except ImportError:
    IFD = None


APP_NAME = "BYLICKILABS Image Metadata Inspector"
APP_VERSION = "1.0.0"

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".jfif",
    ".png", ".webp", ".tif", ".tiff",
    ".bmp", ".gif", ".ico", ".pcx", ".ppm", ".pgm", ".pbm",
    ".avif", ".heic", ".heif", ".jxl",
}


def _json_safe(value: Any, *, max_bytes_preview: int = 96) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        preview = value[:max_bytes_preview]
        return {
            "type": "bytes",
            "length": len(value),
            "hex_preview": preview.hex(),
            "base64_preview": base64.b64encode(preview).decode("ascii"),
            "truncated": len(value) > max_bytes_preview,
        }
    if isinstance(value, bytearray):
        return _json_safe(bytes(value), max_bytes_preview=max_bytes_preview)
    if isinstance(value, dict):
        return {str(k): _json_safe(v, max_bytes_preview=max_bytes_preview) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v, max_bytes_preview=max_bytes_preview) for v in value]
    try:
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            denominator = value.denominator
            return {
                "rational": f"{value.numerator}/{denominator}",
                "decimal": (value.numerator / denominator) if denominator else None,
            }
    except Exception:
        pass
    return str(value)


def _iso_timestamp(timestamp: float) -> str:
    return dt.datetime.fromtimestamp(timestamp).astimezone().isoformat()


def _hash_file(path: Path) -> dict[str, str]:
    algorithms = {
        "MD5": hashlib.md5(),
        "SHA1": hashlib.sha1(),
        "SHA256": hashlib.sha256(),
        "SHA512": hashlib.sha512(),
    }
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            for obj in algorithms.values():
                obj.update(chunk)
    return {name: obj.hexdigest() for name, obj in algorithms.items()}


def _extract_gps(exif: Any) -> dict[str, Any]:
    gps: dict[str, Any] = {}
    try:
        gps_ifd = None
        if IFD is not None and hasattr(exif, "get_ifd"):
            gps_ifd = exif.get_ifd(IFD.GPSInfo)
        if not gps_ifd:
            gps_ifd = exif.get(34853)
        if isinstance(gps_ifd, dict):
            for key, value in gps_ifd.items():
                name = ExifTags.GPSTAGS.get(key, str(key))
                gps[name] = _json_safe(value)
    except Exception as exc:
        gps["_error"] = str(exc)

    def ratio_to_float(v: Any) -> float:
        try:
            return float(v)
        except Exception:
            if isinstance(v, (tuple, list)) and len(v) == 2 and v[1]:
                return float(v[0]) / float(v[1])
            raise

    def dms_to_decimal(values: Any, ref: str) -> float | None:
        try:
            deg, minute, sec = [ratio_to_float(x) for x in values]
            result = deg + minute / 60.0 + sec / 3600.0
            if ref.upper() in ("S", "W"):
                result *= -1
            return result
        except Exception:
            return None

    raw_lat = gps_ifd.get(2) if isinstance(gps_ifd, dict) else None
    raw_lat_ref = gps_ifd.get(1) if isinstance(gps_ifd, dict) else None
    raw_lon = gps_ifd.get(4) if isinstance(gps_ifd, dict) else None
    raw_lon_ref = gps_ifd.get(3) if isinstance(gps_ifd, dict) else None
    if raw_lat and raw_lat_ref and raw_lon and raw_lon_ref:
        lat = dms_to_decimal(raw_lat, str(raw_lat_ref))
        lon = dms_to_decimal(raw_lon, str(raw_lon_ref))
        if lat is not None and lon is not None:
            gps["DecimalLatitude"] = lat
            gps["DecimalLongitude"] = lon
    return gps


def _extract_exif(image: Image.Image) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        exif = image.getexif()
    except Exception as exc:
        return {"_error": str(exc)}

    if not exif:
        return result

    for tag_id, value in exif.items():
        tag_name = ExifTags.TAGS.get(tag_id, f"Tag_{tag_id}")
        if tag_name == "GPSInfo":
            continue
        result[tag_name] = _json_safe(value)

    if IFD is not None and hasattr(exif, "get_ifd"):
        nested: dict[str, Any] = {}
        for ifd_name in ("Exif", "Interop", "GPSInfo", "Makernote"):
            if not hasattr(IFD, ifd_name):
                continue
            try:
                ifd_obj = exif.get_ifd(getattr(IFD, ifd_name))
                if not ifd_obj:
                    continue
                converted = {}
                for key, value in ifd_obj.items():
                    if ifd_name == "GPSInfo":
                        name = ExifTags.GPSTAGS.get(key, str(key))
                    else:
                        name = ExifTags.TAGS.get(key, str(key))
                    converted[name] = _json_safe(value)
                nested[ifd_name] = converted
            except Exception as exc:
                nested[ifd_name] = {"_error": str(exc)}
        if nested:
            result["NestedIFDs"] = nested

    gps = _extract_gps(exif)
    if gps:
        result["GPS"] = gps
    return result


def _extract_iptc(image: Image.Image) -> dict[str, Any]:
    try:
        info = IptcImagePlugin.getiptcinfo(image)
    except Exception as exc:
        return {"_error": str(exc)}
    if not info:
        return {}
    result: dict[str, Any] = {}
    for key, value in info.items():
        if isinstance(key, tuple) and len(key) == 2:
            key_name = f"{key[0]}:{key[1]}"
        else:
            key_name = str(key)
        if isinstance(value, bytes):
            try:
                result[key_name] = value.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    result[key_name] = value.decode("latin-1")
                except Exception:
                    result[key_name] = _json_safe(value)
        else:
            result[key_name] = _json_safe(value)
    return result


def _extract_icc(image: Image.Image) -> dict[str, Any]:
    profile = image.info.get("icc_profile")
    if not profile:
        return {}
    result: dict[str, Any] = {"ProfileBytes": len(profile) if isinstance(profile, (bytes, bytearray)) else None}
    try:
        cms_profile = ImageCms.ImageCmsProfile(profile)
        getters = {
            "Name": "getProfileName",
            "Description": "getProfileDescription",
            "Info": "getProfileInfo",
            "Manufacturer": "getProfileManufacturer",
            "Model": "getProfileModel",
            "Copyright": "getProfileCopyright",
        }
        for key, method_name in getters.items():
            method = getattr(ImageCms, method_name, None)
            if method:
                try:
                    value = method(cms_profile)
                    if value:
                        result[key] = str(value).strip()
                except Exception:
                    pass
    except Exception as exc:
        result["ParseError"] = str(exc)
    return result


def _decode_xml_bytes(blob: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be", "latin-1"):
        try:
            return blob.decode(encoding).strip("\x00\ufeff\r\n ")
        except UnicodeDecodeError:
            continue
    return blob.decode("utf-8", errors="replace")


def _extract_xmp_from_file(path: Path, image: Image.Image | None = None) -> dict[str, Any]:
    packets: list[str] = []
    if image is not None:
        for key in ("xmp", "XML:com.adobe.xmp", "Raw profile type xmp"):
            value = image.info.get(key)
            if isinstance(value, bytes):
                packets.append(_decode_xml_bytes(value))
            elif isinstance(value, str) and value.strip():
                packets.append(value.strip())

    try:
        data = path.read_bytes()
        patterns = [
            rb"<\?xpacket[\s\S]*?<\?xpacket\s+end=['\"][wr]['\"]\s*\?>",
            rb"<x:xmpmeta[\s\S]*?</x:xmpmeta>",
            rb"<rdf:RDF[\s\S]*?</rdf:RDF>",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, data, flags=re.IGNORECASE):
                text = _decode_xml_bytes(match)
                if text and text not in packets:
                    packets.append(text)
    except Exception as exc:
        return {"_error": str(exc), "Packets": packets}

    if not packets:
        return {}
    return {"PacketCount": len(packets), "Packets": packets}


def _extract_png_text(image: Image.Image) -> dict[str, Any]:
    result: dict[str, Any] = {}
    text_map = getattr(image, "text", None)
    if isinstance(text_map, dict):
        for key, value in text_map.items():
            result[str(key)] = _json_safe(value)
    for key in ("comment", "Comment", "Description", "Software", "Title", "Author"):
        if key in image.info and key not in result:
            result[key] = _json_safe(image.info[key])
    return result


def _extract_image_container(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        with Image.open(path) as image:
            result["Basic"] = {
                "Format": image.format,
                "FormatDescription": getattr(image, "format_description", None),
                "Mode": image.mode,
                "Width": image.width,
                "Height": image.height,
                "Megapixels": round((image.width * image.height) / 1_000_000, 4),
                "AspectRatio": round(image.width / image.height, 6) if image.height else None,
                "Frames": getattr(image, "n_frames", 1),
                "Animated": bool(getattr(image, "is_animated", False)),
            }
            result["PillowInfo"] = _json_safe(dict(image.info))

            exif = _extract_exif(image)
            if exif:
                result["EXIF"] = exif

            iptc = _extract_iptc(image)
            if iptc:
                result["IPTC"] = iptc

            icc = _extract_icc(image)
            if icc:
                result["ICC"] = icc

            text = _extract_png_text(image)
            if text:
                result["TextChunksComments"] = text

            xmp = _extract_xmp_from_file(path, image)
            if xmp:
                result["XMP"] = xmp
    except Exception as exc:
        result["PillowError"] = str(exc)
        xmp = _extract_xmp_from_file(path, None)
        if xmp:
            result["XMP"] = xmp
    return result


def _find_exiftool(custom_path: str | None = None) -> str | None:
    candidates = []
    if custom_path:
        candidates.append(custom_path)
    env_path = os.environ.get("EXIFTOOL_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.extend([
        str(Path.cwd() / "exiftool.exe"),
        str(Path.cwd() / "tools" / "exiftool.exe"),
        "exiftool",
        "exiftool.exe",
    ])
    for candidate in candidates:
        if Path(candidate).is_file():
            return str(Path(candidate).resolve())
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _extract_exiftool(path: Path, custom_path: str | None = None) -> dict[str, Any]:
    executable = _find_exiftool(custom_path)
    if not executable:
        return {
            "Status": "not_installed",
            "Message": "ExifTool wurde nicht gefunden. Der interne Scanner funktioniert weiterhin; ExifTool erweitert die Abdeckung proprietärer Metadaten.",
        }
    try:
        command = [
            executable,
            "-j",
            "-G0:1:2",
            "-a",
            "-u",
            "-s",
            "-struct",
            "-charset", "filename=UTF8",
            str(path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
        if completed.returncode not in (0, 1):
            return {"Status": "error", "ReturnCode": completed.returncode, "Error": completed.stderr.strip()}
        parsed = json.loads(completed.stdout or "[]")
        payload = parsed[0] if parsed else {}
        return {
            "Status": "ok",
            "Executable": executable,
            "Metadata": _json_safe(payload),
            "Warnings": completed.stderr.strip() or None,
        }
    except Exception as exc:
        return {"Status": "error", "Executable": executable, "Error": str(exc)}


def _extract_c2pa(path: Path) -> dict[str, Any]:
    try:
        import c2pa
    except Exception as exc:
        return {
            "Status": "sdk_not_installed",
            "Present": None,
            "Message": "C2PA-SDK nicht installiert. Installiere 'c2pa-python', um Content Credentials/C2PA-Manifeste zu lesen und zu validieren.",
            "ImportError": str(exc),
        }

    try:
        with c2pa.Context.from_dict({
            "verify": {
                "remote_manifest_fetch": False,
                "ocsp_fetch": False,
            }
        }) as context:
            with c2pa.Reader(str(path), context=context) as reader:
                raw_json = reader.json()
                parsed = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                active = parsed.get("active_manifest") if isinstance(parsed, dict) else None
                manifests = parsed.get("manifests", {}) if isinstance(parsed, dict) else {}
                present = bool(active or manifests)

                result: dict[str, Any] = {
                    "Status": "ok",
                    "Present": present,
                    "Embedded": None,
                    "RemoteURL": None,
                    "ActiveManifest": active,
                    "ManifestStore": _json_safe(parsed),
                }
                try:
                    result["Embedded"] = bool(reader.is_embedded())
                except Exception:
                    pass
                try:
                    result["RemoteURL"] = reader.get_remote_url()
                except Exception:
                    pass
                try:
                    state = reader.get_validation_state()
                    result["ValidationState"] = _json_safe(state)
                except Exception:
                    pass
                try:
                    validation = reader.get_validation_results()
                    result["ValidationResults"] = _json_safe(validation)
                except Exception:
                    pass
                try:
                    detailed = reader.detailed_json()
                    if detailed:
                        result["DetailedManifestStore"] = _json_safe(json.loads(detailed) if isinstance(detailed, str) else detailed)
                except Exception:
                    pass
                return result
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        no_manifest_markers = (
            "no claim", "no manifest", "manifest not found", "not found", "jumbf", "provenance",
        )
        no_manifest = any(marker in lowered for marker in no_manifest_markers)
        return {
            "Status": "no_manifest" if no_manifest else "read_error",
            "Present": False if no_manifest else None,
            "Error": message,
        }


def extract_metadata(path: str | os.PathLike[str], *, use_exiftool: bool = True, exiftool_path: str | None = None, use_c2pa: bool = True) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    stat = file_path.stat()
    mime, encoding = mimetypes.guess_type(file_path.name)

    result: dict[str, Any] = {
        "Application": {"Name": APP_NAME, "Version": APP_VERSION},
        "File": {
            "Name": file_path.name,
            "Path": str(file_path),
            "Extension": file_path.suffix.lower(),
            "MIME": mime,
            "Encoding": encoding,
            "SizeBytes": stat.st_size,
            "Created": _iso_timestamp(stat.st_ctime),
            "Modified": _iso_timestamp(stat.st_mtime),
            "Accessed": _iso_timestamp(stat.st_atime),
        },
        "Hashes": _hash_file(file_path),
        "ImageMetadata": _extract_image_container(file_path),
    }

    if use_c2pa:
        result["C2PA_ContentCredentials"] = _extract_c2pa(file_path)
    else:
        result["C2PA_ContentCredentials"] = {"Status": "disabled", "Present": None}

    if use_exiftool:
        result["ExifTool_DeepScan"] = _extract_exiftool(file_path, exiftool_path)
    else:
        result["ExifTool_DeepScan"] = {"Status": "disabled"}

    return result


def flatten_dict(data: Any, prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            new_prefix = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(flatten_dict(value, new_prefix))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            rows.extend(flatten_dict(value, f"{prefix}[{index}]"))
    else:
        if data is None:
            text = ""
        elif isinstance(data, (str, int, float, bool)):
            text = str(data)
        else:
            text = json.dumps(_json_safe(data), ensure_ascii=False)
        rows.append((prefix, text))
    return rows


def export_json(results: dict[str, Any], output_path: str | os.PathLike[str]) -> None:
    Path(output_path).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def export_csv(results: dict[str, Any], output_path: str | os.PathLike[str]) -> None:
    with Path(output_path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Datei", "Metadatenpfad", "Wert"])
        for file_name, payload in results.items():
            for key, value in flatten_dict(payload):
                writer.writerow([file_name, key, value])