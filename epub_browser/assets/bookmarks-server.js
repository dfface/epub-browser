/* Session-only adapter. Excluded from static exports by AssetPublisher. */
(function(root) {
    root.EpubBookmarkServerStore = function(book) {
        var base = '/api/bookmarks/' + encodeURIComponent(book);
        if (root.EpubBrowserURL) base=root.EpubBrowserURL.publicPath(base);
        async function request(path,method,data) {
            var options={method:method,headers:{'Content-Type':'application/json'}};
            if(data) options.body=JSON.stringify(data);
            var response=await root.EpubBrowserAuth.fetch(base+path,options);
            if(!response.ok) throw Error('Bookmark request failed');
            return (await response.json()).data;
        }
        return {list:function(){return request('','GET');},add:function(data){return request('','POST',data);},
            rename:function(id,name){return request('/'+encodeURIComponent(id),'PATCH',{name:name});},
            remove:function(id){return request('/'+encodeURIComponent(id),'DELETE');}};
    };
})(window);
