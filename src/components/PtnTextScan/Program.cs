using AssetStudio;
using System.Collections;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Runtime.Versioning;
[assembly: SupportedOSPlatform("windows7.0")]
Console.OutputEncoding = new UTF8Encoding(false);
if (args.Length<2) throw new ArgumentException("PtnTextScan <files root or -> <output> [apk]");
var output=Path.GetFullPath(args[1]);Directory.CreateDirectory(output);
using var lines=new StreamWriter(Path.Combine(output,"Unity文本字段.jsonl"),false,new UTF8Encoding(false));
using var errors=new StreamWriter(Path.Combine(output,"Unity提取错误.jsonl"),false,new UTF8Encoding(false));
var seen=new HashSet<string>();int bundles=0,assets=0,textAssets=0,fields=0,bad=0;
var utf8=new UTF8Encoding(false,true);
void Error(string source,Exception ex){bad++;errors.WriteLine(JsonSerializer.Serialize(new{source,error=ex.Message}));errors.Flush();}
void TextFields(object? value,string path,string source,string cab,long id,int depth=0){
 if(depth>16||value==null)return;
 if(value is string text){if(text.Length>0&&(text.Any(ch=>ch>='\u3400'&&ch<='\u9fff')||path.EndsWith("m_Text",StringComparison.OrdinalIgnoreCase))){lines.WriteLine(JsonSerializer.Serialize(new{source,cab,pathId=id.ToString(),field=path,text}));fields++;}return;}
 if(value is IDictionary dictionary){foreach(DictionaryEntry entry in dictionary){string key=entry.Key?.ToString()??"";if(key is "_bytes" or "m_IndexBuffer" or "m_VertexData" or "image data")continue;TextFields(entry.Value,path+"/"+key,source,cab,id,depth+1);}return;}
 if(value is byte[])return;
 if(value is IEnumerable sequence){int i=0;foreach(var entry in sequence){TextFields(entry,path+"/"+i,source,cab,id,depth+1);i++;}}
}
void Serialized(Stream stream,string name,string source){
 stream.Position=0;string hash=Convert.ToHexString(SHA256.HashData(stream));if(!seen.Add(hash))return;stream.Position=0;
 using var reader=new FileReader(name,new NonClosingStream(stream));if(reader.FileType!=FileType.AssetsFile)return;
 var file=new SerializedFile(reader,new AssetsManager());assets++;
 foreach(var info in file.m_Objects){
  if(info.classID!=(int)ClassIDType.TextAsset&&info.classID!=(int)ClassIDType.MonoBehaviour)continue;
  try{
   var objectReader=new ObjectReader(reader,file,info);
   if(info.classID==(int)ClassIDType.TextAsset){
    var textAsset=new TextAsset(objectReader);string safe=new string(textAsset.m_Name.Select(c=>Path.GetInvalidFileNameChars().Contains(c)?'_':c).ToArray());if(safe.Length>80)safe=safe[..80];
    var directory=Path.Combine(output,"TextAsset");Directory.CreateDirectory(directory);string target=Path.Combine(directory,safe+"_"+info.m_PathID+"_"+hash[..8]+".bytes");File.WriteAllBytes(target,textAsset.m_Script);textAssets++;
    string? text=null;try{text=utf8.GetString(textAsset.m_Script);if(text.Any(c=>c<32&&c!='\n'&&c!='\r'&&c!='\t'))text=null;}catch(DecoderFallbackException){}
    if(text!=null)File.WriteAllText(Path.ChangeExtension(target,".txt"),text,new UTF8Encoding(false));
    lines.WriteLine(JsonSerializer.Serialize(new{source,cab=name,pathId=info.m_PathID.ToString(),name=textAsset.m_Name,raw=Path.GetRelativePath(output,target),text}));
   }else{
    var mono=new MonoBehaviour(objectReader);
    if(mono.serializedType?.m_Type?.m_Nodes?.Any(n=>n.m_Type=="string"&&n.m_Name!="m_Name")==true)TextFields(mono.ToType(),"",source,name,info.m_PathID);
   }
  }catch(Exception ex){Error(source+"/"+info.m_PathID,ex);}
 }
}
void Process(Stream stream,string name,string source){
 var header=new byte[60];stream.Position=0;if(stream.Read(header)<60)return;stream.Position=0;
 bool encrypted=Enumerable.Range(0,7).All(i=>(byte)(header[50+i]^header[57])==Encoding.ASCII.GetBytes("UnityFS")[i]);
 bool standard=header.AsSpan(0,7).SequenceEqual(Encoding.ASCII.GetBytes("UnityFS"));
 if(encrypted||standard){using var reader=new FileReader(name,new NonClosingStream(stream));var bundle=new BundleFile(reader);foreach(var file in bundle.fileList){using(file.stream)Serialized(file.stream,file.path,source);}bundles++;}
 else Serialized(stream,name,source);
 if((bundles+assets)%250==0){Console.WriteLine($"已扫描包 {bundles}，资产文件 {assets}，TextAsset {textAssets}，文本字段 {fields}，错误 {bad}");lines.Flush();}
}
void Builtin(string directory,string source){
 var manager=new AssetsManager();manager.SetAssetFilter(ClassIDType.TextAsset,ClassIDType.MonoBehaviour);
 try{manager.LoadFilesAndFolders(directory);foreach(var file in manager.assetsFileList)foreach(var ob in file.Objects){if(ob is TextAsset ta){string folder=Path.Combine(output,"内置TextAsset");Directory.CreateDirectory(folder);string path=Path.Combine(folder,Path.GetFileName(file.fileName)+"_"+ob.m_PathID+".bytes");File.WriteAllBytes(path,ta.m_Script);textAssets++;string? text=null;try{text=utf8.GetString(ta.m_Script);if(text.Any(c=>c<32&&c!='\n'&&c!='\r'&&c!='\t'))text=null;}catch{}if(text!=null)File.WriteAllText(Path.ChangeExtension(path,".txt"),text,new UTF8Encoding(false));lines.WriteLine(JsonSerializer.Serialize(new{source,cab=file.fileName,pathId=ob.m_PathID.ToString(),name=ta.m_Name,text}));}else if(ob is MonoBehaviour mb)TextFields(mb.ToType(),"",source,file.fileName,ob.m_PathID);}}catch(Exception ex){Error(source,ex);}finally{manager.Clear();}
}
if(args[0]!="-"){
 var root=Path.GetFullPath(args[0]);
 foreach(var directory in new[]{"fs","fsclassify","fstier1","fstier2"}){
  string folder=Path.Combine(root,directory);if(!Directory.Exists(folder))continue;
  foreach(var path in Directory.EnumerateFiles(folder,"*.bundle",SearchOption.AllDirectories))try{using var stream=File.OpenRead(path);Process(stream,path,Path.GetRelativePath(root,path));}catch(Exception ex){Error(path,ex);}
 }
 var chunks=Path.Combine(root,"fschunk");
 if(Directory.Exists(chunks))foreach(var path in Directory.EnumerateFiles(chunks,"*.bin"))try{
  using var stream=File.OpenRead(path);long pos=0;
  while(pos<stream.Length){stream.Position=pos;var h=new byte[160];int count=stream.Read(h);if(count<60)throw new InvalidDataException("Truncated chunk");byte key=h[7];for(int i=0;i<count;i++)h[i]^=key;if(!h.AsSpan(0,8).SequenceEqual(Encoding.ASCII.GetBytes("UnityFS\0")))throw new InvalidDataException("Unsupported chunk header");int q=12;for(int i=0;i<2;i++){q=Array.IndexOf(h,(byte)0,q)+1;if(q<=0)throw new InvalidDataException("Invalid version string");}long length=System.Buffers.Binary.BinaryPrimitives.ReadInt64BigEndian(h.AsSpan(q,8));if(length<60||length>stream.Length-pos||length>int.MaxValue)throw new InvalidDataException("Invalid bundle size");stream.Position=pos;var data=new byte[(int)length];stream.ReadExactly(data);using var memory=new MemoryStream(data,false);Process(memory,path,Path.GetRelativePath(root,path)+"@"+pos);pos+=length;}
 }catch(Exception ex){Error(path,ex);}
 var builtin=Path.Combine(root,"fs","assets","bin","Data");
 if(Directory.Exists(builtin)){
  // The loader may merge .split files: work on a copy to preserve input files.
  var copy=Path.Combine(output,"_工作文件","loose_builtin");Directory.CreateDirectory(copy);
  foreach(var path in Directory.EnumerateFiles(builtin,"*",SearchOption.AllDirectories)){var target=Path.Combine(copy,Path.GetRelativePath(builtin,path));Directory.CreateDirectory(Path.GetDirectoryName(target)!);File.Copy(path,target,true);}
  Builtin(copy,builtin);
 }
}
if(args.Length>2&&File.Exists(args[2])){
 using var archive=ZipFile.OpenRead(args[2]);
 foreach(var entry in archive.Entries.Where(e=>e.FullName.StartsWith("assets/")&&e.FullName.EndsWith(".bundle")))try{using var memory=new MemoryStream();using(var input=entry.Open())input.CopyTo(memory);Process(memory,entry.FullName,Path.GetFileName(args[2])+"!"+entry.FullName);}catch(Exception ex){Error(entry.FullName,ex);}
 var copy=Path.GetFullPath(Path.Combine(output,"_工作文件","apk_builtin"));Directory.CreateDirectory(copy);
 foreach(var entry in archive.Entries.Where(e=>e.FullName.StartsWith("assets/bin/Data/")&&!e.FullName.EndsWith("/")))try{var target=Path.GetFullPath(Path.Combine(copy,entry.FullName["assets/bin/Data/".Length..]));if(!target.StartsWith(copy+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Unsafe APK entry path");Directory.CreateDirectory(Path.GetDirectoryName(target)!);using var input=entry.Open();using var dest=File.Create(target);input.CopyTo(dest);}catch(Exception ex){Error(entry.FullName,ex);}
 Builtin(copy,Path.GetFileName(args[2])+"!assets/bin/Data");
}
lines.Flush();
File.WriteAllText(Path.Combine(output,"Unity扫描报告.json"),JsonSerializer.Serialize(new{bundles,assets,textAssets,fields,errors=bad},new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine($"DONE 包 {bundles} / TextAsset {textAssets} / 字段 {fields} / 错误 {bad}");
if(bad>0)Environment.ExitCode=2;
class NonClosingStream(Stream inner):Stream{
 public override bool CanRead=>inner.CanRead;public override bool CanSeek=>inner.CanSeek;public override bool CanWrite=>false;public override long Length=>inner.Length;public override long Position{get=>inner.Position;set=>inner.Position=value;}
 public override int Read(byte[] b,int o,int n)=>inner.Read(b,o,n);public override long Seek(long o,SeekOrigin s)=>inner.Seek(o,s);public override void Flush(){}public override void SetLength(long n)=>throw new NotSupportedException();public override void Write(byte[] b,int o,int n)=>throw new NotSupportedException();
}
