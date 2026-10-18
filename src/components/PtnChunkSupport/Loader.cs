using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using AssetStudio;
[assembly: System.Runtime.Versioning.TargetFramework(".NETCoreApp,Version=v6.0")]
namespace PtnChunkSupport
{
    // Hooks the path overload only. Each contained bundle still goes through the
    // original PtN decoder and AssetsManager's CAB/resource registration logic.
    public static class Loader
    {
        private static readonly MethodInfo LoadBundle = typeof(AssetsManager).GetMethod(
            "LoadBundleFile", BindingFlags.Instance | BindingFlags.NonPublic,
            null, new[] { typeof(FileReader), typeof(string) }, null);

        public static bool TryLoadChunk(AssetsManager manager, string path)
        {
            if (!string.Equals(Path.GetExtension(path), ".bin", StringComparison.OrdinalIgnoreCase)) return false;
            using var source = File.OpenRead(path);
            var header = new byte[160];
            int initial = ReadUpTo(source, header, header.Length);
            if (initial < 60 || !IsHeader(header, initial)) return false;
            try
            {
                // Validate every boundary before loading any entry. A truncated
                // tail must never silently fall back to loading just entry one.
                var entries = ReadEntries(source);
                Logger.Info("PtN chunk: " + path + " (" + entries.Count + " bundles)");
                foreach (var entry in entries)
                {
                    source.Position = entry.Offset;
                    var data = new byte[entry.Length];
                    if (ReadUpTo(source, data, data.Length) != data.Length) throw new EndOfStreamException();
                    using var reader = new FileReader(path + "#" + entry.Offset, new MemoryStream(data, false));
                    LoadBundle.Invoke(manager, new object[] { reader, path });
                }
            }
            catch (Exception e)
            {
                Logger.Error("Unable to read PtN chunk " + path, e is TargetInvocationException && e.InnerException != null ? e.InnerException : e);
            }
            return true;
        }

        // -1 means this is not a PtN chunk; the original GUI should handle it.
        public static int ExtractChunk(string path, string savePath, string unityVersion)
        {
            if (!string.Equals(Path.GetExtension(path), ".bin", StringComparison.OrdinalIgnoreCase)) return -1;
            using var source = File.OpenRead(path);
            var header = new byte[160]; int initial = ReadUpTo(source, header, header.Length);
            if (initial < 60 || !IsHeader(header, initial)) return -1;
            int written = 0;
            try
            {
                foreach (var entry in ReadEntries(source))
                {
                    source.Position = entry.Offset; var data = new byte[entry.Length];
                    if (ReadUpTo(source, data, data.Length) != data.Length) throw new EndOfStreamException();
                    using var reader = new FileReader(path + "#" + entry.Offset, new MemoryStream(data, false));
                    var bundle = new BundleFile(reader, unityVersion);
                    var folder = Path.Combine(savePath, Path.GetFileName(path) + "_unpacked", entry.Offset.ToString(System.Globalization.CultureInfo.InvariantCulture));
                    Directory.CreateDirectory(folder);
                    foreach (var file in bundle.fileList)
                    {
                        using (file.stream)
                        {
                            var target = Path.Combine(folder, Path.GetFileName(file.path));
                            if (File.Exists(target)) continue;
                            file.stream.Position = 0;
                            using var destination = File.Create(target); file.stream.CopyTo(destination); written++;
                        }
                    }
                }
            }
            catch (Exception e) { Logger.Error("Unable to extract PtN chunk " + path, e); }
            return written;
        }

        private static List<(long Offset, int Length)> ReadEntries(Stream source)
        {
            var entries = new List<(long Offset, int Length)>(); var header = new byte[160]; long pos = 0;
            while (pos < source.Length)
            {
                source.Position = pos; int count = ReadUpTo(source, header, header.Length);
                if (count < 60 || !IsHeader(header, count)) throw new InvalidDataException("Invalid chunk header at " + pos);
                byte key = header[7]; for (int i = 0; i < count; i++) header[i] ^= key;
                int q = 12;
                for (int i = 0; i < 2; i++)
                {
                    q = Array.IndexOf(header, (byte)0, q, count - q) + 1;
                    if (q <= 0) throw new InvalidDataException("Unterminated Unity version");
                }
                if (q + 8 > count) throw new InvalidDataException("Missing bundle length");
                long length = System.Buffers.Binary.BinaryPrimitives.ReadInt64BigEndian(header.AsSpan(q, 8));
                if (length < 60 || length > source.Length - pos || length > int.MaxValue)
                    throw new InvalidDataException("Invalid bundle length at " + pos);
                entries.Add((pos, (int)length)); pos += length;
            }
            return entries;
        }

        private static bool IsHeader(byte[] data, int count)
        {
            byte key = data[7]; var magic = Encoding.ASCII.GetBytes("UnityFS\0");
            for (int i = 0; i < magic.Length; i++) if ((byte)(data[i] ^ key) != magic[i]) return false;
            return true;
        }
        private static int ReadUpTo(Stream stream, byte[] data, int count)
        {
            int total = 0, n;
            while (total < count && (n = stream.Read(data, total, count - total)) > 0) total += n;
            return total;
        }
    }
}
