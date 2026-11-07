// Transport adapter only: keep the native solver, input deck and physical equations unchanged.
using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

class ShortPathSolver
{
    const string ExpectedSolverHash = "__SOLVER_SHA256__";

    static string Hash(string path)
    {
        using (var stream = File.OpenRead(path))
        using (var hash = SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }

    static int Main(string[] args)
    {
        try
        {
            if (args.Length != 2 || args[0] != "-i" || !Regex.IsMatch(args[1], "^[A-Za-z0-9_-]{1,48}$"))
                throw new Exception("Expected a plain CalculiX job name");
            string name = args[1];
            string original = Directory.GetCurrentDirectory();
            string solver = Environment.GetEnvironmentVariable("ROCKETWRIGHT_CALCULIX_NATIVE");
            string scratch = Environment.GetEnvironmentVariable("ROCKETWRIGHT_FEM_SCRATCH");
            if (String.IsNullOrEmpty(solver) || String.IsNullOrEmpty(scratch))
                throw new Exception("Native solver and short scratch directory must be configured");
            solver = Path.GetFullPath(solver);
            if (Hash(solver) != ExpectedSolverHash)
                throw new Exception("Native solver differs from the hash bound into this adapter");
            scratch = Path.Combine(Path.GetFullPath(scratch), Guid.NewGuid().ToString("N"));
            if (scratch.Length > 190 || original.Length > 235)
                throw new Exception("A shorter output/scratch path is required");
            string input = Path.Combine(original, name + ".inp");
            if (Regex.IsMatch(File.ReadAllText(input), @"^\s*\*INCLUDE", RegexOptions.Multiline | RegexOptions.IgnoreCase))
                throw new Exception("Only self-contained input decks are supported");
            Directory.CreateDirectory(scratch);
            string deck = Path.Combine(scratch, name + ".inp");
            File.Copy(input, deck, false);
            string inputHash = Hash(input);
            if (Hash(deck) != inputHash) throw new Exception("Input transfer changed the deck");
            var start = new ProcessStartInfo(solver, "-i " + name);
            start.WorkingDirectory = scratch;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            int code;
            using (var process = Process.Start(start))
            {
                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs line)
                    { if (line.Data != null) Console.WriteLine(line.Data); };
                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs line)
                    { if (line.Data != null) Console.Error.WriteLine(line.Data); };
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                process.WaitForExit();
                code = process.ExitCode;
            }
            var audit = new StringBuilder();
            audit.AppendLine("native_solver_sha256\t" + ExpectedSolverHash);
            audit.AppendLine("input_sha256\t" + inputHash);
            audit.AppendLine("exit_code\t" + code);
            audit.AppendLine("original_name\tstored_name\tsha256");
            int index = 0;
            foreach (string path in Directory.GetFiles(scratch))
            {
                string file = Path.GetFileName(path);
                if (file == name + ".inp") continue;
                string saved = file;
                if (Path.Combine(original, saved).Length >= 255)
                    saved = name + "-a" + (index++).ToString("D3") + Path.GetExtension(file);
                string target = Path.Combine(original, saved);
                File.Copy(path, target, false);
                string hash = Hash(path);
                if (Hash(target) != hash) throw new Exception("Output transfer changed a file");
                audit.AppendLine(file + "\t" + saved + "\t" + hash);
            }
            if (Hash(input) != inputHash || Hash(deck) != inputHash)
                throw new Exception("Input deck changed during solver execution");
            File.WriteAllText(Path.Combine(original, name + "-transport.tsv"), audit.ToString());
            return code;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("Solver transport failed: " + error.Message);
            return 86;
        }
    }
}
