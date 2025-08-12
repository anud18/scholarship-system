const testConfigurationId = async () => {
  console.log('🧪 Testing configuration_id transmission...')
  
  // Test the eligible scholarships API first
  const eligibleResponse = await fetch('http://localhost:8000/api/v1/scholarships/eligible', {
    method: 'GET',
    headers: {
      'Authorization': 'Bearer your-test-token', // Replace with actual token
      'Content-Type': 'application/json'
    }
  });
  
  if (eligibleResponse.ok) {
    const eligibleData = await eligibleResponse.json();
    console.log('📚 Eligible scholarships response:');
    console.log('   Success:', eligibleData.success);
    console.log('   Data count:', eligibleData.data?.length || 0);
    
    if (eligibleData.success && eligibleData.data && eligibleData.data.length > 0) {
      const firstScholarship = eligibleData.data[0];
      console.log('   First scholarship:');
      console.log('     - Name:', firstScholarship.name);
      console.log('     - Code:', firstScholarship.code);
      console.log('     - Configuration ID:', firstScholarship.configuration_id);
      
      if (firstScholarship.configuration_id && firstScholarship.configuration_id > 0) {
        console.log('✅ Configuration ID is present in eligible scholarships');
        
        // Test application creation with this configuration_id
        const applicationData = {
          scholarship_type: firstScholarship.code,
          configuration_id: firstScholarship.configuration_id,
          scholarship_subtype_list: ['general'],
          form_data: {
            fields: {
              test_field: {
                field_id: 'test_field',
                field_type: 'text',
                value: 'test value',
                required: true
              }
            },
            documents: []
          },
          agree_terms: true
        };
        
        console.log('📝 Testing application creation with configuration_id:', firstScholarship.configuration_id);
        
        const createResponse = await fetch('http://localhost:8000/api/v1/applications/?is_draft=true', {
          method: 'POST',
          headers: {
            'Authorization': 'Bearer your-test-token', // Replace with actual token
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(applicationData)
        });
        
        const createResult = await createResponse.json();
        console.log('📋 Application creation result:');
        console.log('   Status:', createResponse.status);
        console.log('   Success:', createResult.success);
        if (!createResult.success) {
          console.log('   Error:', createResult.message);
        } else {
          console.log('✅ Application created successfully with configuration_id!');
        }
      } else {
        console.log('❌ Configuration ID is missing or invalid in eligible scholarships');
      }
    } else {
      console.log('❌ No eligible scholarships found');
    }
  } else {
    console.log('❌ Failed to fetch eligible scholarships');
    console.log('   Status:', eligibleResponse.status);
  }
}

// Note: This is a test script. In actual usage, you would run this with proper authentication.
console.log('This is a test script. Run with proper authentication in a real environment.');