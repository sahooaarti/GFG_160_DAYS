#User function Template for python3

# class Solution:
# 	def pushZerosToEnd(self,arr):
# 	    l=len(arr)
# 	    for i in range(l):
# 	        if arr[i]== 0:
# 	            arr[i:]=arr[i+1:]
# 	            arr.append(arr[i])
# 	   return arr
class Solution:
    def pushZerosToEnd(self, arr):
        # Initialize a counter for non-zero elements
        non_zero_idx = 0
        
        # Iterate through the array
        for i in range(len(arr)):
            # If the current element is non-zero
            if arr[i] != 0:
                # Swap the current element with the element at the non-zero index
                arr[non_zero_idx], arr[i] = arr[i], arr[non_zero_idx]
                # Increment the non-zero index
                non_zero_idx += 1
        
        return arr
    	   


#{ 
 # Driver Code Starts
#Initial Template for Python 3

if __name__ == '__main__':
    tc = int(input())
    while tc > 0:
        arr = list(map(int, input().strip().split()))
        ob = Solution()
        ob.pushZerosToEnd(arr)
        for x in arr:
            print(x, end=" ")
        print()
        tc -= 1
# } Driver Code Ends