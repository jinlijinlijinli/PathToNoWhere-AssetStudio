using AssetStudio;
using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
using System.Runtime.Versioning;
[assembly: SupportedOSPlatform("windows7.0")]
Console.OutputEncoding=new UTF8Encoding(false);
var root=Path.GetFullPath(args.Length>0?args[0]:".");
if(args.Contains("--check-chunks")){
 Console.WriteLine($"Validated {Jobs(root,true).Count()} chunk bundle boundaries");
 return;
}
var output=Path.GetFullPath(args.Length>1?args[1]:Path.Combine(root,"提取结果")); var unity=Path.Combine(output,"Unity");Directory.CreateDirectory(unity);
bool append=args.Contains("--append"), chunksOnly=args.Contains("--chunks-only");
var known=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
if(append && File.Exists(Path.Combine(output,"资源索引.jsonl")))foreach(var line in File.ReadLines(Path.Combine(output,"资源索引.jsonl"))){using var doc=JsonDocument.Parse(line);foreach(var n in doc.RootElement.GetProperty("nodes").EnumerateArray())if(n.GetProperty("status").GetString()=="written")known.TryAdd(n.GetProperty("cab").GetString()!,n.GetProperty("sha256").GetString()!);}
using var log=new StreamWriter(Path.Combine(output,"资源索引.jsonl"),append,Encoding.UTF8);
using var err=new StreamWriter(Path.Combine(output,"提取错误.jsonl"),append,Encoding.UTF8);
int good=0,bad=0,unique=0,duplicates=0,collisions=0; long written=0;
foreach(var job in Jobs(root,chunksOnly)) {
 var path=job.Path; string source=Path.GetRelativePath(root,path)+(job.Length>0?$"@{job.Offset}":"");
 using var fs=File.OpenRead(path); fs.Position=job.Offset;var h=new byte[60];if(fs.Read(h)<60)continue;
 if(!Enumerable.Range(0,7).All(i=>(byte)(h[50+i]^h[57])==Encoding.ASCII.GetBytes("UnityFS")[i]))continue;
 try { fs.Position=job.Offset; Stream input=fs;if(job.Length>0){var data=new byte[checked((int)job.Length)];fs.ReadExactly(data);input=new MemoryStream(data,false);} using var r=new FileReader(path,input);var b=new BundleFile(r);var nodes=new List<object>();
  foreach(var sf in b.fileList) {
   using var stream=sf.stream;stream.Position=0;var hash=Convert.ToHexString(SHA256.HashData(stream));string filename=Path.GetFileName(sf.path);string target=Path.Combine(unity,filename);string status="written";
   if(known.TryGetValue(filename,out var old)) {
    if(old==hash){duplicates++;status="duplicate";}else {collisions++;target=Path.Combine(output,"conflicts",Path.GetRelativePath(root,path)+(job.Length>0?$"_{job.Offset}":""),filename);Directory.CreateDirectory(Path.GetDirectoryName(target)!);}
   }else known[filename]=hash;
   if(status!="duplicate"){stream.Position=0;using var dest=File.Create(target);stream.CopyTo(dest);unique++;written+=stream.Length;}
   var deps=new List<string>();var names=new List<string>();int objects=0;string version="";
   stream.Position=0;
   // Metadata and bundle containers provide an index without loading every object into memory.
   using(var rr=new FileReader(sf.path,new NonClosingStream(stream)))if(rr.FileType==FileType.AssetsFile){var a=new SerializedFile(rr,new AssetsManager());objects=a.m_Objects.Count;version=a.unityVersion;deps.AddRange(a.m_Externals.Select(e=>Path.GetFileName(e.pathName)));
    foreach(var oi in a.m_Objects.Where(o=>o.classID==(int)ClassIDType.AssetBundle)){var ab=new AssetBundle(new ObjectReader(rr,a,oi));names.Add(ab.m_Name);names.AddRange(ab.m_Container.Select(c=>c.Key));}
   }
   nodes.Add(new{cab=filename,sha256=hash,target=Path.GetRelativePath(output,target),status,objects,version,deps,names});
  }
  good++;log.WriteLine(JsonSerializer.Serialize(new{source,nodes}));
 }catch(Exception e){bad++;err.WriteLine(JsonSerializer.Serialize(new{source,error=e.ToString()}));err.Flush();}
 if((good+bad)%500==0){Console.WriteLine($"Bundles {good}, errors {bad}, files {unique}, duplicates {duplicates}, conflicts {collisions}, GiB {written/1073741824.0:F2}");log.Flush();}
}
File.WriteAllText(Path.Combine(output,append?"chunk-summary.json":"summary.json"),JsonSerializer.Serialize(new{bundles=good,errors=bad,files=unique,duplicates,collisions,bytes=written},new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine($"DONE {good} bundles / {bad} errors / {unique} files / {collisions} conflicts");
static IEnumerable<(string Path,long Offset,long Length)> Jobs(string root,bool chunksOnly){
 if(!chunksOnly)foreach(var dir in new[]{"fs/assets","fsclassify/assets"})if(Directory.Exists(Path.Combine(root,dir)))foreach(var p in Directory.EnumerateFiles(Path.Combine(root,dir),"*.bundle",SearchOption.AllDirectories))yield return(p,0,0);
 var chunks=Path.Combine(root,"fschunk");if(!Directory.Exists(chunks))yield break;
 foreach(var p in Directory.EnumerateFiles(chunks,"*.bin").OrderBy(p=>p,StringComparer.Ordinal)){
  using var f=File.OpenRead(p);long pos=0;
  var h=new byte[160];
  while(pos<f.Length){
   f.Position=pos;int count=(int)Math.Min(h.Length,f.Length-pos);f.ReadExactly(h.AsSpan(0,count));
   if(!HasChunkHeader(h,count)){
    int padding=(int)((64-(pos&63))&63);
    if(padding==0||padding>count||h.AsSpan(0,padding).ContainsAnyExcept((byte)0))
     throw new InvalidDataException($"Invalid chunk header {p}@{pos}");
    pos+=padding;
    if(pos==f.Length)break;
    f.Position=pos;count=(int)Math.Min(h.Length,f.Length-pos);f.ReadExactly(h.AsSpan(0,count));
    if(!HasChunkHeader(h,count))throw new InvalidDataException($"Invalid aligned chunk header {p}@{pos}");
   }
   byte key=h[7];for(int i=0;i<count;i++)h[i]^=key;
   int q=12;for(int i=0;i<2;i++){q=Array.IndexOf(h,(byte)0,q,count-q)+1;if(q<=0)throw new InvalidDataException("Invalid version string");}
   if(q+8>count)throw new InvalidDataException($"Missing bundle length {p}@{pos}");
   long length=System.Buffers.Binary.BinaryPrimitives.ReadInt64BigEndian(h.AsSpan(q,8));if(length<60||length>f.Length-pos||length>int.MaxValue)throw new InvalidDataException($"Invalid bundle size {length} at {p}@{pos}");
   yield return(p,pos,length);pos+=length;
  }
 }
}
static bool HasChunkHeader(byte[] h,int count){
 if(count<60)return false;
 for(int i=0;i<8;i++)if((h[i]^h[7])!="UnityFS\0"u8[i])return false;
 return true;
}
class NonClosingStream(Stream inner):Stream {
 public override bool CanRead=>inner.CanRead;public override bool CanSeek=>inner.CanSeek;public override bool CanWrite=>false;public override long Length=>inner.Length;public override long Position{get=>inner.Position;set=>inner.Position=value;}
 public override int Read(byte[] b,int o,int n)=>inner.Read(b,o,n); public override long Seek(long o,SeekOrigin s)=>inner.Seek(o,s);public override void Flush(){}public override void SetLength(long n)=>throw new NotSupportedException();public override void Write(byte[] b,int o,int n)=>throw new NotSupportedException();
}
