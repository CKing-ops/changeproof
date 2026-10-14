import java.io.BufferedReader;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.PrintStream;
import java.lang.reflect.Array;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

// Calls one public method per input line and prints what it returned or threw (changeproof Java behaviour check).
// Line: binary class, method, static|instance, parameter types, observer methods, then one token per argument
// ("~" for null, "=" and base64 text otherwise). Reply: "ok" and the base64 rendering, or "timeout".
public final class Probe {
    private static final long LIMIT_MS = 2000;
    private static final int MAX_TEXT = 100_000;

    private Probe() {
    }

    // PURPOSE: READS CASES FROM STDIN AND WRITES ONE REPLY LINE PER CASE; THE CODE UNDER TEST CANNOT WRITE TO STDOUT
    public static void main(String[] args) throws Exception {
        PrintStream out = new PrintStream(new FileOutputStream(FileDescriptor.out), true, StandardCharsets.UTF_8);
        PrintStream sink = new PrintStream(OutputStream.nullOutputStream());
        System.setOut(sink);
        System.setErr(sink);
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        ExecutorService worker = worker();
        String line;
        while ((line = in.readLine()) != null) {
            String[] fields = line.split("\t", -1);
            Future<String> result = worker.submit(() -> call(fields));
            String reply;
            try {
                reply = "ok\t" + encode(result.get(LIMIT_MS, TimeUnit.MILLISECONDS));
            } catch (TimeoutException e) {
                worker.shutdownNow();
                worker = worker();
                reply = "timeout";
            } catch (ExecutionException e) {
                reply = "ok\t" + encode("error=" + e.getCause().getClass().getName());
            }
            out.println(reply);
        }
        out.flush();
        Runtime.getRuntime().halt(0);
    }

    // PURPOSE: A DAEMON THREAD TO RUN CASES ON, SO A CASE THAT NEVER RETURNS CANNOT KEEP THE PROBE ALIVE
    private static ExecutorService worker() {
        return Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task);
            thread.setDaemon(true);
            return thread;
        });
    }

    // PURPOSE: RUNS ONE CASE: BUILDS THE ARGUMENTS, CALLS THE METHOD (TWICE ON AN INSTANCE), THEN EACH OBSERVER
    private static String call(String[] f) {
        StringBuilder text = new StringBuilder();
        Object self = null;
        Class<?> type = null;
        try {
            type = Class.forName(f[0], false, Probe.class.getClassLoader());
            String[] names = f[3].isEmpty() ? new String[0] : f[3].split(",");
            Class<?>[] kinds = new Class<?>[names.length];
            Object[] values = new Object[names.length];
            for (int i = 0; i < names.length; i++) {
                kinds[i] = typeOf(names[i]);
                values[i] = valueOf(names[i], f[5 + i]);
            }
            Method method = type.getMethod(f[1], kinds);
            if (f[2].equals("instance")) {
                self = type.getConstructor().newInstance();
            }
            text.append("return=").append(render(method.invoke(self, values)));
            if (self != null) {
                // A second call on the same object shows state the first call left behind.
                text.append(";again=").append(outcome(self, method, values));
            }
        } catch (InvocationTargetException e) {
            text.append("throw=").append(e.getCause().getClass().getName());
        } catch (Throwable e) {
            return "error=" + e.getClass().getName();
        }
        if (self != null && !f[4].isEmpty()) {
            for (String name : f[4].split(",")) {
                try {
                    text.append(';').append(name).append('=').append(outcome(self, type.getMethod(name)));
                } catch (NoSuchMethodException e) {
                    text.append("error:").append(e.getClass().getName());
                }
            }
        }
        return text.length() > MAX_TEXT ? text.substring(0, MAX_TEXT) + "...(" + text.length() + " chars)" : text.toString();
    }

    // PURPOSE: WHAT ONE CALL RETURNED OR THREW, AS TEXT
    private static String outcome(Object self, Method method, Object... values) {
        try {
            return render(method.invoke(self, values));
        } catch (InvocationTargetException e) {
            return "throw:" + e.getCause().getClass().getName();
        } catch (Throwable e) {
            return "error:" + e.getClass().getName();
        }
    }

    // PURPOSE: THE CLASS FOR A PARAMETER TYPE NAME THE PYTHON SIDE SENDS
    private static Class<?> typeOf(String name) {
        return switch (name) {
            case "int" -> int.class;
            case "long" -> long.class;
            case "short" -> short.class;
            case "byte" -> byte.class;
            case "char" -> char.class;
            case "boolean" -> boolean.class;
            case "double" -> double.class;
            case "float" -> float.class;
            case "Integer" -> Integer.class;
            case "Long" -> Long.class;
            case "Boolean" -> Boolean.class;
            case "Double" -> Double.class;
            case "String", "CharSequence" -> name.equals("String") ? String.class : CharSequence.class;
            case "byte[]" -> byte[].class;
            case "int[]" -> int[].class;
            case "long[]" -> long[].class;
            case "String[]" -> String[].class;
            default -> throw new IllegalArgumentException(name);
        };
    }

    // PURPOSE: ONE ARGUMENT FROM ITS TOKEN
    private static Object valueOf(String name, String token) {
        if (token.equals("~")) {
            return null;
        }
        String text = decode(token.substring(1));
        return switch (name) {
            case "int", "Integer" -> Integer.parseInt(text);
            case "long", "Long" -> Long.parseLong(text);
            case "short" -> Short.parseShort(text);
            case "byte" -> Byte.parseByte(text);
            case "char" -> text.charAt(0);
            case "boolean", "Boolean" -> Boolean.parseBoolean(text);
            case "double", "Double" -> Double.parseDouble(text);
            case "float" -> Float.parseFloat(text);
            case "byte[]" -> {
                String[] parts = items(text);
                byte[] found = new byte[parts.length];
                for (int i = 0; i < parts.length; i++) {
                    found[i] = Byte.parseByte(parts[i]);
                }
                yield found;
            }
            case "int[]" -> {
                String[] parts = items(text);
                int[] found = new int[parts.length];
                for (int i = 0; i < parts.length; i++) {
                    found[i] = Integer.parseInt(parts[i]);
                }
                yield found;
            }
            case "long[]" -> {
                String[] parts = items(text);
                long[] found = new long[parts.length];
                for (int i = 0; i < parts.length; i++) {
                    found[i] = Long.parseLong(parts[i]);
                }
                yield found;
            }
            case "String[]" -> {
                String[] parts = items(text);
                for (int i = 0; i < parts.length; i++) {
                    parts[i] = decode(parts[i]);
                }
                yield parts;
            }
            default -> text;
        };
    }

    // PURPOSE: COMMA-SEPARATED ITEMS OF AN ARRAY ARGUMENT; AN EMPTY TEXT IS AN EMPTY ARRAY
    private static String[] items(String text) {
        return text.isEmpty() ? new String[0] : text.split(",", -1);
    }

    // PURPOSE: A VALUE AS TEXT THAT IS THE SAME FOR EQUAL VALUES, ARRAYS ELEMENT BY ELEMENT
    private static String render(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String s) {
            return '"' + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + '"';
        }
        if (value instanceof Character c) {
            return "'" + c + "'";
        }
        if (value.getClass().isArray()) {
            StringBuilder text = new StringBuilder("[");
            for (int i = 0; i < Array.getLength(value); i++) {
                text.append(i == 0 ? "" : ",").append(render(Array.get(value, i)));
            }
            return text.append(']').toString();
        }
        return value.getClass().getName() + ":" + value;
    }

    // PURPOSE: BASE64 OF UTF-8 TEXT
    private static String encode(String text) {
        return Base64.getEncoder().encodeToString(text.getBytes(StandardCharsets.UTF_8));
    }

    // PURPOSE: UTF-8 TEXT FROM BASE64
    private static String decode(String text) {
        return new String(Base64.getDecoder().decode(text), StandardCharsets.UTF_8);
    }
}
