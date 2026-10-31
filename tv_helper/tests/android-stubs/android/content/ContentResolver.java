package android.content;import android.net.Uri;import android.database.*;public abstract class ContentResolver {
 public abstract Cursor query(Uri u,String[] p,String s,String[] a,String o);public abstract Uri insert(Uri u,ContentValues v);public abstract int update(Uri u,ContentValues v,String s,String[] a);public abstract int delete(Uri u,String s,String[] a);
 public void registerContentObserver(Uri u,boolean b,ContentObserver o){}public void unregisterContentObserver(ContentObserver o){}
}
