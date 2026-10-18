using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;
using System.Text.Json.Nodes;
var original=Path.GetFullPath(args[0]);var helper=Path.GetFullPath(args[1]);var output=Path.GetFullPath(args[2]);
using var asm=AssemblyDefinition.ReadAssembly(original);
using var support=AssemblyDefinition.ReadAssembly(helper);
var type=asm.MainModule.Types.Single(t=>t.FullName=="AssetStudio.AssetsManager");
var method=type.Methods.Single(m=>m.Name=="LoadFile"&&m.Parameters.Count==1&&m.Parameters[0].ParameterType.FullName=="System.String");
if(method.Body.Instructions.Any(i=>i.Operand is MethodReference r&&r.DeclaringType.FullName=="PtnChunkSupport.Loader"))throw new InvalidOperationException("Already patched");
var hook=asm.MainModule.ImportReference(support.MainModule.Types.Single(t=>t.FullName=="PtnChunkSupport.Loader").Methods.Single(m=>m.Name=="TryLoadChunk"));
var il=method.Body.GetILProcessor();var first=method.Body.Instructions[0];
foreach(var instruction in new[]{il.Create(OpCodes.Ldarg_0),il.Create(OpCodes.Ldarg_1),il.Create(OpCodes.Call,hook),il.Create(OpCodes.Brfalse,first),il.Create(OpCodes.Ret)})il.InsertBefore(first,instruction);
asm.Write(output);
var guiPath=Path.Combine(Path.GetDirectoryName(original)!,"AssetStudioModGUI-PtN.dll");
using(var gui=AssemblyDefinition.ReadAssembly(guiPath)){
 var studio=gui.MainModule.Types.Single(t=>t.FullName=="AssetStudioGUI.Studio");
 var extract=studio.Methods.Single(m=>m.Name=="ExtractFile"&&m.Parameters.Count==2&&m.Parameters[0].ParameterType.FullName=="System.String");
 var managerField=gui.MainModule.ImportReference(studio.Fields.Single(f=>f.Name=="assetsManager"));
 var versionField=gui.MainModule.ImportReference(type.Fields.Single(f=>f.Name=="SpecifyUnityVersion"));
 var extractHook=gui.MainModule.ImportReference(support.MainModule.Types.Single(t=>t.FullName=="PtnChunkSupport.Loader").Methods.Single(m=>m.Name=="ExtractChunk"));
 var result=new VariableDefinition(gui.MainModule.TypeSystem.Int32);extract.Body.Variables.Add(result);extract.Body.InitLocals=true;
 var ep=extract.Body.GetILProcessor();var entry=extract.Body.Instructions[0];
 foreach(var i in new[]{ep.Create(OpCodes.Ldarg_0),ep.Create(OpCodes.Ldarg_1),ep.Create(OpCodes.Ldsfld,managerField),ep.Create(OpCodes.Ldfld,versionField),ep.Create(OpCodes.Call,extractHook),ep.Create(OpCodes.Stloc,result),ep.Create(OpCodes.Ldloc,result),ep.Create(OpCodes.Ldc_I4_0),ep.Create(OpCodes.Blt,entry),ep.Create(OpCodes.Ldloc,result),ep.Create(OpCodes.Ret)})ep.InsertBefore(entry,i);
 var integration=support.MainModule.Types.SingleOrDefault(t=>t.FullName=="PtnChunkSupport.Live2DIntegration");
 if(integration!=null){
  var form=gui.MainModule.Types.Single(t=>t.FullName=="AssetStudioGUI.AssetStudioGUIForm");
  var install=gui.MainModule.ImportReference(integration.Methods.Single(m=>m.Name=="Install"));
  foreach(var ctor in form.Methods.Where(m=>m.IsConstructor&&!m.IsStatic&&m.HasBody)){
   var cp=ctor.Body.GetILProcessor();foreach(var ret in ctor.Body.Instructions.Where(i=>i.OpCode==OpCodes.Ret).ToArray()){cp.InsertBefore(ret,cp.Create(OpCodes.Ldarg_0));cp.InsertBefore(ret,cp.Create(OpCodes.Call,install));}
  }
 }
 gui.Write(Path.Combine(Path.GetDirectoryName(output)!,"AssetStudioModGUI-PtN.dll"));
}
var depsName="AssetStudioModGUI-PtN.deps.json";
var deps=JsonNode.Parse(File.ReadAllText(Path.Combine(Path.GetDirectoryName(original)!,depsName)))!;
foreach(var target in deps["targets"]!.AsObject()){
 var t=target.Value!.AsObject();
 var core=t.FirstOrDefault(x=>x.Key.StartsWith("AssetStudio/",StringComparison.Ordinal));
 if(core.Value==null)continue;
 core.Value["dependencies"]??=new JsonObject();core.Value["dependencies"]!["PtnChunkSupport"]="1.0.0";
 t["PtnChunkSupport/1.0.0"]=new JsonObject{["runtime"]=new JsonObject{["PtnChunkSupport.dll"]=new JsonObject()}};
}
deps["libraries"]!["PtnChunkSupport/1.0.0"]=new JsonObject{["type"]="project",["serviceable"]=false,["sha512"]=""};
File.WriteAllText(Path.Combine(Path.GetDirectoryName(output)!,depsName),deps.ToJsonString(new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine(output);
