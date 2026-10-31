package android.net; public class Uri { public final String value; private Uri(String s){value=s;} public static Uri parse(String s){return new Uri(s);} public String toString(){return value;} }
