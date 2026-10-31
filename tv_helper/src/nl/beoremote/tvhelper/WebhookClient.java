package nl.beoremote.tvhelper;
import java.net.*;
import java.io.*;
import org.json.*;

/** Limited local HA capability; no general credential, redirect or retry. */
final class WebhookClient {
    static void validate(String address) throws JSONException {
        try {
            URL u=new URL(address);String h=u.getHost();
            if(!"http".equals(u.getProtocol()) || u.getPort()!=8123 || u.getUserInfo()!=null || u.getQuery()!=null || u.getRef()!=null || !u.getPath().matches("/api/webhook/[a-f0-9]{64}") || !h.matches("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+"))throw new Exception();
            InetAddress a=InetAddress.getByName(h);if(!a.isSiteLocalAddress()||a.isLoopbackAddress())throw new Exception();
        }catch(Exception error){throw new JSONException("callback");}
    }
    static void send(String address,String source,String tv) throws Exception {
        send(address,source,tv,false);
    }
    static void send(String address,String source,String tv,boolean cancel) throws Exception {
        if(address.isEmpty())return;validate(address);
        JSONObject body=new JSONObject();body.put("source",source);body.put("tv",tv);body.put("created_at",System.currentTimeMillis()/1000.0);
        if(cancel)body.put("cancel",true);
        byte[] bytes=body.toString().getBytes("UTF-8");
        HttpURLConnection c=(HttpURLConnection)new URL(address).openConnection(Proxy.NO_PROXY);
        try{c.setConnectTimeout(1500);c.setReadTimeout(1500);c.setInstanceFollowRedirects(false);c.setRequestMethod("POST");c.setRequestProperty("Content-Type","application/json");c.setDoOutput(true);c.setFixedLengthStreamingMode(bytes.length);
            try(OutputStream out=c.getOutputStream()){out.write(bytes);}if(c.getResponseCode()!=200)throw new IOException("delivery");
        }finally{c.disconnect();}
    }
}
