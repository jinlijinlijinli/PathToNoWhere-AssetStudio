using AssetStudio;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System.Runtime.Versioning;
[assembly: SupportedOSPlatform("windows7.0")]
Console.OutputEncoding=new System.Text.UTF8Encoding(false);
if(args.Length<3)throw new ArgumentException("Usage: index.jsonl output model-filter");
var index=Path.GetFullPath(args[0]);var unity=Path.Combine(Path.GetDirectoryName(index)!,"Unity");var output=Path.GetFullPath(args[1]);string filter=args[2];
bool exact=args.Contains("--exact");
bool Matches(string name)=>filter=="*"||(exact?System.Text.RegularExpressions.Regex.IsMatch(name,@"(?<![a-zA-Z0-9])"+System.Text.RegularExpressions.Regex.Escape(filter)+@"(?![a-zA-Z0-9])",System.Text.RegularExpressions.RegexOptions.IgnoreCase):name.Contains(filter,StringComparison.OrdinalIgnoreCase));
foreach(var dir in new[]{"Fade","Moc3Json","Textures","TexturesMeta"})Directory.CreateDirectory(Path.Combine(output,dir));
Console.WriteLine("读取资源索引…");
var selected=new HashSet<string>();
foreach(var line in File.ReadLines(index)){var row=JObject.Parse(line);foreach(var n in row["nodes"]!){var names=n["names"]!.Values<string>().ToArray();if(names.Any(s=>(s!.Contains("live2d",StringComparison.OrdinalIgnoreCase)||s.Contains("animations2d",StringComparison.OrdinalIgnoreCase))&&Matches(s)))selected.Add(n["cab"]!.Value<string>()!);}}
int moc=0,fade=0,texture=0,meta=0;var errors=new List<string>();
foreach(var cab in selected){
 try{var path=Path.Combine(unity,cab);using var reader=new FileReader(path);if(reader.FileType!=FileType.AssetsFile)continue;var assets=new SerializedFile(reader,new AssetsManager());
 foreach(var oi in assets.m_Objects){var or=new ObjectReader(reader,assets,oi);
  try{
   if(or.type==ClassIDType.MonoBehaviour){var ob=new MonoBehaviour(or);var data=ob.ToType();if(data==null)throw new Exception("Missing type tree: "+ob.m_Name);var json=JObject.FromObject(data);string name=json["m_Name"]?.Value<string>()??ob.m_Name;
    if(json["_bytes"]!=null){var b=json["_bytes"]!;byte[] bytes=b.Type==JTokenType.String?Convert.FromBase64String(b.Value<string>()!):b.Values<byte>().ToArray();if(bytes.Length>=4&&System.Text.Encoding.ASCII.GetString(bytes,0,4)=="MOC3"){json["_bytes"]=new JArray(bytes.Select(x=>(int)x));File.WriteAllText(Path.Combine(output,"Moc3Json",Safe(name)+".json"),json.ToString());moc++;}}
    else if(name.Contains(".fade",StringComparison.OrdinalIgnoreCase)){File.WriteAllText(Path.Combine(output,"Fade",Safe(name)+" @"+ob.m_PathID+".json"),json.ToString());fade++;}
   }else if(or.type==ClassIDType.Texture2D){var t=new Texture2D(or);if(t.m_Name.StartsWith("texture_0",StringComparison.OrdinalIgnoreCase)){using var s=t.ConvertToStream(ImageFormat.Png,true);if(s==null)throw new Exception("Texture decode failed");File.WriteAllBytes(Path.Combine(output,"Textures",Safe(t.m_Name)+" @"+t.m_PathID+".png"),s.ToArray());texture++;}}
   else if(or.type==ClassIDType.AssetBundle){var ab=new AssetBundle(or);if(System.Text.RegularExpressions.Regex.IsMatch(ab.m_Name,@"\.(1024|2048|4096)\.bundle$")){File.WriteAllBytes(Path.Combine(output,"TexturesMeta",Safe(ab.m_Name)+".dat"),ab.GetRawData());meta++;}}
  }catch(Exception e){errors.Add(cab+" / "+or.type+": "+e.Message);}
 }
 }catch(Exception e){errors.Add(cab+": "+e.Message);}
 Console.WriteLine($"{cab}: moc {moc} fade {fade} textures {texture} meta {meta}");
}
var report=new{selected=selected.Count,moc,fade,texture,meta,errors};File.WriteAllText(Path.Combine(output,"export-report.json"),JsonConvert.SerializeObject(report,Formatting.Indented));Console.WriteLine(JsonConvert.SerializeObject(report,Formatting.Indented));if(moc==0)Environment.ExitCode=1;
static string Safe(string s){foreach(var ch in Path.GetInvalidFileNameChars())s=s.Replace(ch,'_');return s;}
